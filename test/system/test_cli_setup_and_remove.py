from conftest import (
    run_smb_zfs_command,
    get_system_user_exists,
    get_zfs_dataset_exists,
    read_smb_conf,
    get_zfs_property,
    check_smb_zfs_result
)
from smb_zfs.config_generator import MACOS_SETTINGS


# --- Initial Setup State Tests ---
def test_initial_setup_state(initial_state):
    """Verify the state after the initial setup in the fixture."""
    assert initial_state['primary_pool'] == 'primary_testpool'
    assert 'secondary_testpool' in initial_state['secondary_pools']
    assert 'tertiary_testpool' in initial_state['secondary_pools']
    assert initial_state['workgroup'] == 'TESTGROUP'
    assert initial_state['server_name'] == 'TESTSERVER'
    assert get_zfs_dataset_exists('primary_testpool/homes')


def test_setup_with_options():
    """Test setup command with various options."""
    # This test needs to be run without the fixture to test setup independently
    # First clean up
    run_smb_zfs_command("remove --delete-users --delete-data --yes")
  
    # Test setup with macOS optimization and default quota
    run_smb_zfs_command(
        "setup --primary-pool primary_testpool --secondary-pools secondary_testpool --server-name MACSERVER --workgroup MACGROUP --macos --default-home-quota 20G")

    state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert state['workgroup'] == 'MACGROUP'
    assert state['server_name'] == 'MACSERVER'
    assert 'workgroup = MACGROUP' in smb_conf
    assert 'server string = MACSERVER' in smb_conf


# --- Setup Modification Tests ---
def test_modify_setup_remove_secondary_pool(initial_state):
    """Test modifying setup to remove a secondary pool."""
    run_smb_zfs_command(
        "modify setup --remove-secondary-pools tertiary_testpool --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'tertiary_testpool' not in final_state['secondary_pools']
    assert 'secondary_testpool' in final_state['secondary_pools']
    assert not get_zfs_dataset_exists('tertiary_testpool/homes')
    assert not get_zfs_dataset_exists('tertiary_testpool/shares')


def test_modify_setup_change_server_settings(initial_state):
    """Test changing server name and workgroup."""
    run_smb_zfs_command(
        "modify setup --server-name NEWSERVER --workgroup NEWGROUP --json")
    final_state = run_smb_zfs_command("get-state")
    smb_conf_content = read_smb_conf()

    assert final_state['workgroup'] == 'NEWGROUP'
    assert final_state['server_name'] == 'NEWSERVER'
    assert 'workgroup = NEWGROUP' in smb_conf_content
    assert 'server string = NEWSERVER' in smb_conf_content


def test_modify_setup_change_primary_pool(initial_state):
    """Test changing the primary pool with data migration."""
    # Create a user first to have data to migrate
    
    cmd = "create user sztest_migrateuser --password 'TestPassword!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "User 'sztest_migrateuser' created successfully.", json=True)

    # Change primary pool with data migration
    cmd = "modify setup --primary-pool secondary_testpool --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, '', json=True)

    final_state = run_smb_zfs_command("get-state")

    assert final_state['primary_pool'] == 'secondary_testpool'
    # User data should now be on the new primary pool
    assert get_zfs_dataset_exists('secondary_testpool/homes/sztest_migrateuser')


def test_modify_setup_macos_toggle(initial_state):
    """Test toggling macOS optimization."""
    # Enable macOS optimization
    run_smb_zfs_command("modify setup --macos --json")
    assert MACOS_SETTINGS in read_smb_conf()
    
    # Disable macOS optimization
    run_smb_zfs_command("modify setup --no-macos --json")
    assert MACOS_SETTINGS not in read_smb_conf()


def test_modify_setup_default_home_quota(initial_state):
    """Test changing default home quota."""
    run_smb_zfs_command("modify setup --default-home-quota 50G --json")
    final_state = run_smb_zfs_command("get-state")

    # New users should get the default quota
    run_smb_zfs_command(
        "create user sztest_quotauser --password 'TestPassword!' --json")

    assert get_zfs_property('primary_testpool/homes/sztest_quotauser', 'quota') == '50G'


# --- Remove Command Tests ---
def test_remove_command_complete(initial_state):
    """
    Test the remove command. This is implicitly tested by the teardown fixture,
    but we can have an explicit test too.
    """
    # Create a user to ensure there's something to delete
    run_smb_zfs_command(
        "create user sztest_testuser --password TestPassword123 --json")
    assert get_system_user_exists('sztest_testuser')

    # Run remove
    run_smb_zfs_command("remove --delete-users --delete-data --yes --json")

    # Verify cleanup
    assert not get_system_user_exists('sztest_testuser')
    assert not get_zfs_dataset_exists('primary_testpool/homes')
    assert not get_zfs_dataset_exists('primary_testpool/shares')
    result = run_smb_zfs_command("get-state")
    assert result == "Error: System not set up. Run 'setup' first."


def test_remove_partial_cleanup(initial_state):
    """Test remove command with partial cleanup options."""
    # Create test data
    run_smb_zfs_command(
        "create user sztest_removeuser --password 'TestPassword!' --json")
    run_smb_zfs_command(
        "create share removeshare --dataset shares/removeshare --json")

    # Remove only users, keep data
    run_smb_zfs_command("remove --delete-users --yes --json")

    # Users should be gone but datasets should remain
    assert not get_system_user_exists('sztest_removeuser')
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_removeuser')
    assert get_zfs_dataset_exists('primary_testpool/shares/removeshare')


def test_remove_data_only():
    """Test remove command that only removes data."""
    # Setup fresh environment
    run_smb_zfs_command("remove --delete-users --delete-data --yes")

    run_smb_zfs_command(
        "setup --primary-pool primary_testpool --secondary-pools secondary_testpool")

    # Create test data
    run_smb_zfs_command(
        "create user sztest_datauser --password 'TestPassword!' --json")
    run_smb_zfs_command(
        "create share datashare --dataset shares/datashare --json")

    # Remove only data, keep users
    run_smb_zfs_command("remove --delete-data --yes --json")

    # Users should still exist but datasets should be gone
    assert get_system_user_exists('sztest_datauser')
    assert not get_zfs_dataset_exists('primary_testpool/homes/sztest_datauser')
    assert not get_zfs_dataset_exists('primary_testpool/shares/datashare')
