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
def test_initial_setup_state(initial_state) -> None:
    """Verify the state after the initial setup in the fixture."""
    assert initial_state['primary_pool'] == 'primary_testpool'
    assert 'secondary_testpool' in initial_state['secondary_pools']
    assert 'tertiary_testpool' in initial_state['secondary_pools']
    assert initial_state['workgroup'] == 'TESTGROUP'
    assert initial_state['server_name'] == 'TESTSERVER'

    # Check ZFS datasets exist
    assert get_zfs_dataset_exists('primary_testpool/homes')

    # Check smb.conf configuration
    smb_conf = read_smb_conf()
    assert 'workgroup = TESTGROUP' in smb_conf
    assert 'server string = TESTSERVER' in smb_conf


def test_setup_with_options() -> None:
    """Test setup command with various options."""
    # This test needs to be run without the fixture to test setup independently
    # First clean up
    cmd_cleanup = "remove --delete-users --delete-data --yes"
    result_cleanup = run_smb_zfs_command(cmd_cleanup)
    # Note: cleanup might return error if nothing to clean, that's OK

    # Test setup with macOS optimization and default quota
    cmd = "setup --primary-pool primary_testpool --secondary-pools secondary_testpool --server-name MACSERVER --workgroup MACGROUP --macos --default-home-quota 20G --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Setup completed successfully.", json=True)

    # Check state
    state = run_smb_zfs_command("get-state")
    assert state['workgroup'] == 'MACGROUP'
    assert state['server_name'] == 'MACSERVER'
    assert state['macos_optimized'] == True
    assert state['default_home_quota'] == '20G'
    assert state['primary_pool'] == 'primary_testpool'
    assert 'secondary_testpool' in state['secondary_pools']

    # Check ZFS datasets
    assert get_zfs_dataset_exists('primary_testpool/homes')

    # Check smb.conf
    smb_conf = read_smb_conf()
    assert 'workgroup = MACGROUP' in smb_conf
    assert 'server string = MACSERVER' in smb_conf
    # Check for macOS settings
    assert MACOS_SETTINGS in smb_conf


# --- Setup Modification Tests ---
def test_modify_setup_remove_secondary_pool(initial_state) -> None:
    """Test modifying setup to remove a secondary pool."""
    cmd = "modify setup --remove-secondary-pools tertiary_testpool --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Global setup modified successfully.", json=True)

    # Check state
    final_state = run_smb_zfs_command("get-state")
    assert 'tertiary_testpool' not in final_state['secondary_pools']
    assert 'secondary_testpool' in final_state['secondary_pools']

    # Check ZFS cleanup
    assert not get_zfs_dataset_exists('tertiary_testpool/')
    # Verify other pools still exist
    assert get_zfs_dataset_exists('primary_testpool/homes')


def test_modify_setup_change_server_settings(initial_state) -> None:
    """Test changing server name and workgroup."""
    cmd = "modify setup --server-name NEWSERVER --workgroup NEWGROUP --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Global setup modified successfully.", json=True)

    # Check state
    final_state = run_smb_zfs_command("get-state")
    assert final_state['workgroup'] == 'NEWGROUP'
    assert final_state['server_name'] == 'NEWSERVER'

    # Check smb.conf
    smb_conf_content = read_smb_conf()
    assert 'workgroup = NEWGROUP' in smb_conf_content
    assert 'server string = NEWSERVER' in smb_conf_content
    # Ensure old settings are gone
    assert 'workgroup = TESTGROUP' not in smb_conf_content
    assert 'server string = TESTSERVER' not in smb_conf_content


def test_modify_setup_change_primary_pool(initial_state) -> None:
    """Test changing the primary pool with data migration."""
    # Create a user first to have data to migrate
    cmd1 = "create user sztest_migrateuser --password 'TestPassword!' --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(
        result1, "User 'sztest_migrateuser' created successfully.", json=True)

    # Verify user exists on original primary pool
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_migrateuser')
    assert get_system_user_exists('sztest_migrateuser')

    # Change primary pool with data migration
    cmd2 = "modify setup --primary-pool secondary_testpool --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(
        result2, "Global setup modified successfully.", json=True)

    # Check state
    final_state = run_smb_zfs_command("get-state")
    assert final_state['primary_pool'] == 'secondary_testpool'

    # Check user data migration
    assert get_zfs_dataset_exists(
        'secondary_testpool/homes/sztest_migrateuser')
    assert not get_zfs_dataset_exists(
        'primary_testpool/homes/sztest_migrateuser')
    assert get_system_user_exists('sztest_migrateuser')

    # Check ZFS properties maintained
    home_path = get_zfs_property(
        'secondary_testpool/homes/sztest_migrateuser', 'mountpoint')
    assert '/secondary_testpool/homes/sztest_migrateuser' == home_path 


def test_modify_setup_macos_toggle(initial_state) -> None:
    """Test toggling macOS optimization."""
    # Enable macOS optimization
    cmd1 = "modify setup --macos --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(
        result1, "Global setup modified successfully.", json=True)

    # Check state
    state1 = run_smb_zfs_command("get-state")
    assert state1['macos_optimized'] == True

    # Check smb.conf
    smb_conf1 = read_smb_conf()
    for setting in MACOS_SETTINGS.split('\n'):
        if setting.strip():
            assert setting.strip() in smb_conf1

    # Disable macOS optimization
    cmd2 = "modify setup --no-macos --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(
        result2, "Global setup modified successfully.", json=True)

    # Check state
    state2 = run_smb_zfs_command("get-state")
    assert state2['macos_optimized'] == False

    # Check smb.conf
    smb_conf2 = read_smb_conf()
    for setting in MACOS_SETTINGS.split('\n'):
        if setting.strip():
            assert setting.strip() not in smb_conf2


def test_modify_setup_default_home_quota(initial_state) -> None:
    """Test changing default home quota."""
    cmd1 = "modify setup --default-home-quota 50G --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(
        result1, "Global setup modified successfully.", json=True)

    # Check state
    final_state = run_smb_zfs_command("get-state")
    assert final_state['default_home_quota'] == '50G'

    # New users should get the default quota
    cmd2 = "create user sztest_quotauser --password 'TestPassword!' --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(
        result2, "User 'sztest_quotauser' created successfully.", json=True)

    # Check ZFS quota applied
    assert get_zfs_property(
        'primary_testpool/homes/sztest_quotauser', 'quota') == '50G'

    # Check system user
    assert get_system_user_exists('sztest_quotauser')

    # Check state consistency
    final_state2 = run_smb_zfs_command("get-state")
    assert final_state2['users']['sztest_quotauser']['dataset']['quota'] == '50G'


# --- Remove Command Tests ---
def test_remove_command_complete(initial_state) -> None:
    """
    Test the remove command. This is implicitly tested by the teardown fixture,
    but we can have an explicit test too.
    """
    # Create a user to ensure there's something to delete
    cmd1 = "create user sztest_testuser --password 'TestPassword123!' --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(
        result1, "User 'sztest_testuser' created successfully.", json=True)

    # Verify user exists
    assert get_system_user_exists('sztest_testuser')
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_testuser')

    # Run remove
    cmd2 = "remove --delete-users --delete-data --yes --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Removal completed successfully.", json=True)

    # Verify cleanup
    assert not get_system_user_exists('sztest_testuser')
    assert not get_zfs_dataset_exists('primary_testpool/homes')
    assert not get_zfs_dataset_exists('primary_testpool/shares')
    assert not get_zfs_dataset_exists('secondary_testpool/homes')
    assert not get_zfs_dataset_exists('secondary_testpool/shares')
    assert not get_zfs_dataset_exists('tertiary_testpool/homes')
    assert not get_zfs_dataset_exists('tertiary_testpool/shares')

    # Verify state is cleared
    result3 = run_smb_zfs_command("get-state")
    check_smb_zfs_result(
        result3, "Error: System not set up. Run 'setup' first.", is_error=True)


def test_remove_partial_cleanup(initial_state) -> None:
    """Test remove command with partial cleanup options."""
    # Create test data
    cmd1 = "create user sztest_removeuser --password 'TestPassword!' --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(
        result1, "User 'sztest_removeuser' created successfully.", json=True)

    cmd2 = "create share removeshare --dataset shares/removeshare --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(
        result2, "Share 'removeshare' created successfully.", json=True)

    # Verify initial state
    assert get_system_user_exists('sztest_removeuser')
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_removeuser')
    assert get_zfs_dataset_exists('primary_testpool/shares/removeshare')

    # Remove only users, keep data
    cmd3 = "remove --delete-users --yes --json"
    result3 = run_smb_zfs_command(cmd3)
    check_smb_zfs_result(result3, "Removal completed successfully.", json=True)

    # Users should be gone but datasets should remain
    assert not get_system_user_exists('sztest_removeuser')
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_removeuser')
    assert get_zfs_dataset_exists('primary_testpool/shares/removeshare')

    # Check smb.conf
    smb_conf = read_smb_conf()
    assert '[removeshare]' in smb_conf


def test_remove_data_only() -> None:
    """Test remove command that only removes data."""
    # Setup fresh environment
    cmd_cleanup = "remove --delete-users --delete-data --yes"
    result_cleanup = run_smb_zfs_command(cmd_cleanup)
    # Cleanup might return error if nothing exists, that's OK

    cmd_setup = "setup --primary-pool primary_testpool --secondary-pools secondary_testpool --json"
    result_setup = run_smb_zfs_command(cmd_setup)
    check_smb_zfs_result(
        result_setup, "Setup completed successfully.", json=True)

    # Create test data
    cmd1 = "create user sztest_datauser --password 'TestPassword!' --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(
        result1, "User 'sztest_datauser' created successfully.", json=True)

    cmd2 = "create share datashare --dataset shares/datashare --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(
        result2, "Share 'datashare' created successfully.", json=True)

    # Verify initial state
    assert get_system_user_exists('sztest_datauser')
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_datauser')
    assert get_zfs_dataset_exists('primary_testpool/shares/datashare')

    # Remove only data, keep users
    cmd3 = "remove --delete-data --yes --json"
    result3 = run_smb_zfs_command(cmd3)
    check_smb_zfs_result(result3, "Removal completed successfully.", json=True)

    # Users should still exist but datasets should be gone
    assert get_system_user_exists('sztest_datauser')
    assert not get_zfs_dataset_exists('primary_testpool/homes/sztest_datauser')
    assert not get_zfs_dataset_exists('primary_testpool/shares/datashare')
    assert not get_zfs_dataset_exists('primary_testpool/homes')

    # Check smb.conf
    smb_conf = read_smb_conf()
    assert '[datashare]' not in smb_conf
