from conftest import (
    run_smb_zfs_command,
    get_system_user_exists,
    get_system_group_exists,
    get_system_user_details,
    get_zfs_dataset_exists,
    get_zfs_property,
    read_smb_conf,
    check_wizard_output
)
from smb_zfs.const import CONFIRM_PHRASE


def test_wizard_create_user_basic(initial_state) -> None:
    """Test creating a simple user via the wizard and verify all changes."""
    cmd = "wizard create user"
    inputs = [
        "sztest_w_user1",      # Username
        "SecretPassword1!",     # Password
        "SecretPassword1!",     # Confirm Password
        "n",                   # No shell access
        "y",                   # Create home directory
        ""                     # No additional groups
    ]
    result = run_smb_zfs_command(cmd, user_inputs=inputs)
    check_wizard_output(result, "User 'sztest_w_user1' created successfully.")

    # Verify state
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_w_user1' in final_state['users']
    assert get_system_user_exists('sztest_w_user1')
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_w_user1')


def test_wizard_delete_user_with_data(initial_state) -> None:
    """Test deleting a user and their data via the wizard."""
    # First, create the user to be deleted
    run_smb_zfs_command(
        "create user sztest_w_todelete --password 'SecretPassword!'")
    assert get_system_user_exists('sztest_w_todelete')
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_w_todelete')

    # Now, run the delete wizard
    cmd = "wizard delete user"
    inputs = [
        "sztest_w_todelete",   # Username to delete
        "y",                   # Yes, delete data
        f"{CONFIRM_PHRASE}"      # Confirmation phrase
    ]
    result = run_smb_zfs_command(cmd, user_inputs=inputs)
    check_wizard_output(
        result, "User 'sztest_w_todelete' deleted successfully.")

    # Verify state
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_w_todelete' not in final_state['users']
    assert not get_system_user_exists('sztest_w_todelete')
    assert not get_zfs_dataset_exists(
        'primary_testpool/homes/sztest_w_todelete')


def test_wizard_create_group_with_users(initial_state) -> None:
    """Test creating a group with initial users via the wizard."""
    # Create users first
    run_smb_zfs_command(
        "create user sztest_w_guser1 --password 'SecretPassword!'")
    run_smb_zfs_command(
        "create user sztest_w_guser2 --password 'SecretPassword!'")

    cmd = "wizard create group"
    inputs = [
        "sztest_w_testgroup",  # Group name
        "A wizard group",      # Description
        "sztest_w_guser1,sztest_w_guser2"  # Initial members
    ]
    result = run_smb_zfs_command(cmd, user_inputs=inputs)
    check_wizard_output(
        result, "Group 'sztest_w_testgroup' created successfully.")

    # Verify state
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_w_testgroup' in final_state['groups']
    assert 'sztest_w_guser1' in final_state['groups']['sztest_w_testgroup']['members']
    assert 'sztest_w_guser2' in final_state['groups']['sztest_w_testgroup']['members']
    assert get_system_group_exists('sztest_w_testgroup')
    assert 'sztest_w_testgroup' in get_system_user_details('sztest_w_guser1')


def test_wizard_create_share_basic(initial_state) -> None:
    """Test creating a basic share via the wizard."""
    cmd = "wizard create share"
    inputs = [
        "w_testshare",                 # Share name
        "primary_testpool",            # Pool
        "shares/w_testshare",          # Dataset path
        "My Wizard Share",             # Comment
        "root",                        # Owner
        "smb_users",                   # Group
        "0775",                        # Permissions
        "@smb_users",                  # Valid users
        "n",                           # Read-only?
        "y",                           # Browseable?
        "15G"                          # Quota
    ]
    result = run_smb_zfs_command(cmd, user_inputs=inputs)
    check_wizard_output(result, "Share 'w_testshare' created successfully.")

    # Verify state
    final_state = run_smb_zfs_command("get-state")
    assert 'w_testshare' in final_state['shares']
    assert final_state['shares']['w_testshare']['dataset']['quota'] == '15G'
    assert get_zfs_dataset_exists('primary_testpool/shares/w_testshare')
    assert get_zfs_property(
        'primary_testpool/shares/w_testshare', 'quota') == '15G'
    smb_conf = read_smb_conf()
    assert '[w_testshare]' in smb_conf
    assert 'comment = My Wizard Share' in smb_conf


def test_wizard_modify_share_rename_and_pool(initial_state) -> None:
    """Test renaming and moving a share via the wizard."""
    # Create the share to be modified
    run_smb_zfs_command(
        "create share w_modshare --dataset shares/w_modshare --pool primary_testpool")

    cmd = "wizard modify share"
    inputs = [
        "w_modshare",              # Share to modify
        "y",                       # Rename share?
        "w_modshare_renamed",      # New name
        "y",                       # Move pool?
        "secondary_testpool",      # New pool
        "",                        # Keep comment
        "",                        # Keep owner
        "",                        # Keep group
        "",                        # Keep perms
        "",                        # Keep valid users
        "n",                       # Keep read-only (no)
        "y",                       # Keep browseable (yes)
        ""                         # Keep quota
    ]
    result = run_smb_zfs_command(cmd, user_inputs=inputs)
    check_wizard_output(result, "Share 'w_modshare' modified successfully.")

    # Verify state
    final_state = run_smb_zfs_command("get-state")
    assert 'w_modshare' not in final_state['shares']
    assert 'w_modshare_renamed' in final_state['shares']
    assert final_state['shares']['w_modshare_renamed']['dataset']['pool'] == 'secondary_testpool'
    assert not get_zfs_dataset_exists('primary_testpool/shares/w_modshare')
    assert get_zfs_dataset_exists(
        'secondary_testpool/shares/w_modshare_renamed')
    smb_conf = read_smb_conf()
    assert '[w_modshare]' not in smb_conf
    assert '[w_modshare_renamed]' in smb_conf
    assert 'path = /secondary_testpool/shares/w_modshare_renamed' in smb_conf


def test_wizard_modify_home_quota(basic_users_and_groups) -> None:
    """Test modifying a user's home quota via the wizard."""
    home_dataset = 'primary_testpool/homes/sztest_user_a'
    assert get_zfs_property(home_dataset, 'quota') == 'none'

    cmd = "wizard modify home"
    inputs = [
        "sztest_user_a",       # User to modify
        "5G"                   # New quota
    ]
    result = run_smb_zfs_command(cmd, user_inputs=inputs)
    check_wizard_output(
        result, "Quota for user 'sztest_user_a' has been set to 5G.")

    # Verify state
    assert get_zfs_property(home_dataset, 'quota') == '5G'
    final_state = run_smb_zfs_command("get-state")
    assert final_state['users']['sztest_user_a']['dataset']['quota'] == '5G'
