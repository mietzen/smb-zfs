from conftest import (
    run_smb_zfs_command,
    get_system_user_exists,
    get_system_user_shell,
    get_system_group_exists,
    get_system_user_details,
    get_zfs_dataset_exists,
    get_zfs_property,
    read_smb_conf,
    get_file_permissions,
    get_owner_and_group,
    check_smb_zfs_result
)


# --- User Creation and Deletion Tests ---

def test_create_user_basic(initial_state) -> None:
    """Test creating a simple user and verify all changes."""
    cmd = "create user sztest_testuser1 --password 'SecretPassword!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "User 'sztest_testuser1' created successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_testuser1' in final_state['users']

    # Verify system state
    assert get_system_user_exists('sztest_testuser1')
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_testuser1')
    assert get_zfs_property(
        'primary_testpool/homes/sztest_testuser1', 'mountpoint') == '/primary_testpool/homes/sztest_testuser1'


def test_create_user_no_home(initial_state) -> None:
    """Test creating a user with no home directory and verify all changes."""
    cmd = "create user sztest_nohomeuser --password 'SecretPassword!' --no-home --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "User 'sztest_nohomeuser' created successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_nohomeuser' in final_state['users']
    assert 'dataset' not in final_state['users']['sztest_nohomeuser']

    # Verify system state
    assert get_system_user_exists('sztest_nohomeuser')
    assert not get_zfs_dataset_exists('primary_testpool/homes/sztest_nohomeuser')


def test_create_user_with_shell(initial_state) -> None:
    """Test creating a user with shell enabled and verify all changes."""
    cmd = "create user sztest_shelluser --password 'SecretPassword!' --shell --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "User 'sztest_shelluser' created successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_shelluser' in final_state['users']
    assert final_state['users']['sztest_shelluser']['shell_access'] is True

    # Verify system state
    assert get_system_user_exists('sztest_shelluser')
    user_shell = get_system_user_shell('sztest_shelluser')
    assert user_shell is not None and '/bin/bash' in user_shell
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_shelluser')


def test_delete_user_basic(initial_state) -> None:
    """Test deleting a user while keeping their data."""
    # Create user first
    cmd1 = "create user sztest_todelete --password 'SecretPassword!' --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(result1, "User 'sztest_todelete' created successfully.", json=True)
    assert get_system_user_exists('sztest_todelete')
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_todelete')

    # Now delete the user
    cmd2 = "delete user sztest_todelete --yes --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "User 'sztest_todelete' deleted successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_todelete' not in final_state['users']

    # Verify system state
    assert not get_system_user_exists('sztest_todelete')
    # Data should still exist
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_todelete')


def test_delete_user_with_data(initial_state) -> None:
    """Test deleting a user and their data."""
    # Create user first
    cmd1 = "create user sztest_datadelete --password 'SecretPassword!' --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(result1, "User 'sztest_datadelete' created successfully.", json=True)
    assert get_zfs_dataset_exists('primary_testpool/homes/sztest_datadelete')

    # Now delete the user and their data
    cmd2 = "delete user sztest_datadelete --delete-data --yes --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "User 'sztest_datadelete' deleted successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_datadelete' not in final_state['users']

    # Verify system state
    assert not get_system_user_exists('sztest_datadelete')
    assert not get_zfs_dataset_exists('primary_testpool/homes/sztest_datadelete')


# --- Group Creation and Deletion Tests ---

def test_create_group_basic(initial_state) -> None:
    """Test creating a group and verify all changes."""
    cmd = "create group sztest_testgroup1 --description 'A test group' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Group 'sztest_testgroup1' created successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_testgroup1' in final_state['groups']

    # Verify system state
    assert get_system_group_exists('sztest_testgroup1')


def test_create_group_with_users(initial_state) -> None:
    """Test creating a group with initial users and verify all changes."""
    # Create users first
    cmd1 = "create user sztest_groupuser1 --password 'SecretPassword!' --json"
    check_smb_zfs_result(run_smb_zfs_command(cmd1), "User 'sztest_groupuser1' created successfully.", json=True)
    cmd2 = "create user sztest_groupuser2 --password 'SecretPassword!' --json"
    check_smb_zfs_result(run_smb_zfs_command(cmd2), "User 'sztest_groupuser2' created successfully.", json=True)

    # Create group with users
    cmd3 = "create group sztest_testgroup2 --description 'Group with users' --users sztest_groupuser1,sztest_groupuser2 --json"
    result3 = run_smb_zfs_command(cmd3)
    check_smb_zfs_result(result3, "Group 'sztest_testgroup2' created successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_testgroup2' in final_state['groups']
    assert 'sztest_groupuser1' in final_state['groups']['sztest_testgroup2']['members']
    assert 'sztest_groupuser2' in final_state['groups']['sztest_testgroup2']['members']

    # Verify system state
    assert get_system_group_exists('sztest_testgroup2')
    assert 'sztest_testgroup2' in get_system_user_details('sztest_groupuser1')
    assert 'sztest_testgroup2' in get_system_user_details('sztest_groupuser2')


def test_delete_group_basic(initial_state) -> None:
    """Test deleting a group and verify all changes."""
    # Create group first
    cmd1 = "create group sztest_groupdel --description 'Delete me' --json"
    check_smb_zfs_result(run_smb_zfs_command(cmd1), "Group 'sztest_groupdel' created successfully.", json=True)
    assert get_system_group_exists('sztest_groupdel')

    # Now delete the group
    cmd2 = "delete group sztest_groupdel --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Group 'sztest_groupdel' deleted successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_groupdel' not in final_state['groups']

    # Verify system state
    assert not get_system_group_exists('sztest_groupdel')


# --- Share Creation and Deletion Tests ---

def test_create_share_basic(initial_state) -> None:
    """Test creating a samba share and verify all changes."""
    cmd = "create share testshare1 --dataset shares/testshare1 --pool primary_testpool --comment 'My Test Share' --quota 10G --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Share 'testshare1' created successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'testshare1' in final_state['shares']
    assert final_state['shares']['smb']['testshare1']['dataset']['pool'] == 'primary_testpool'
    assert final_state['shares']['smb']['testshare1']['dataset']['quota'] == '10G'

    # Verify system state
    assert get_zfs_dataset_exists('primary_testpool/shares/testshare1')
    assert get_zfs_property('primary_testpool/shares/testshare1', 'quota') == '10G'

    # Verify smb.conf
    smb_conf = read_smb_conf()
    assert '[testshare1]' in smb_conf
    assert 'comment = My Test Share' in smb_conf
    assert 'path = /primary_testpool/shares/testshare1' in smb_conf


def test_create_share_with_permissions(initial_state) -> None:
    """Test creating a share with specific users and permissions."""
    # Create user first
    cmd1 = "create user sztest_shareuser --password 'SecretPassword!' --json"
    check_smb_zfs_result(run_smb_zfs_command(cmd1), "User 'sztest_shareuser' created successfully.", json=True)

    # Create share
    cmd2 = "create share restrictedshare --dataset shares/restrictedshare --pool secondary_testpool --valid-users sztest_shareuser --readonly --no-browse --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Share 'restrictedshare' created successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'restrictedshare' in final_state['shares']
    share_config = final_state['shares']['smb']['restrictedshare']['smb_config']
    assert 'sztest_shareuser' in share_config['valid_users']
    assert share_config['read_only'] is True
    assert share_config['browseable'] is False

    # Verify system state
    assert get_zfs_dataset_exists('secondary_testpool/shares/restrictedshare')

    # Verify smb.conf
    smb_conf = read_smb_conf()
    assert '[restrictedshare]' in smb_conf
    assert 'valid users = sztest_shareuser' in smb_conf
    assert 'read only = yes' in smb_conf
    assert 'browseable = no' in smb_conf


def test_delete_share_basic(initial_state) -> None:
    """Test deleting a share while keeping its data."""
    # Create share first
    cmd1 = "create share deltshare --dataset shares/deltshare --pool primary_testpool --json"
    check_smb_zfs_result(run_smb_zfs_command(cmd1), "Share 'deltshare' created successfully.", json=True)
    assert '[deltshare]' in read_smb_conf()
    assert get_zfs_dataset_exists('primary_testpool/shares/deltshare')

    # Delete share
    cmd2 = "delete share deltshare --yes --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Share 'deltshare' deleted successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'deltshare' not in final_state['shares']

    # Verify smb.conf and system state
    assert '[deltshare]' not in read_smb_conf()
    # Dataset should still exist by default
    assert get_zfs_dataset_exists('primary_testpool/shares/deltshare')


def test_delete_share_with_data(initial_state) -> None:
    """Test deleting a share and its underlying data."""
    # Create share first
    cmd1 = "create share datadeltshare --dataset shares/datadeltshare --pool primary_testpool --json"
    check_smb_zfs_result(run_smb_zfs_command(cmd1), "Share 'datadeltshare' created successfully.", json=True)
    assert get_zfs_dataset_exists('primary_testpool/shares/datadeltshare')

    # Delete share and data
    cmd2 = "delete share datadeltshare --delete-data --yes --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Share 'datadeltshare' deleted successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    assert 'datadeltshare' not in final_state['shares']

    # Verify system state
    assert not get_zfs_dataset_exists('primary_testpool/shares/datadeltshare')


# --- Group Modification Tests ---

def test_modify_group_add_and_remove_users(basic_users_and_groups: None) -> None:
    """Test adding and removing users from a group."""
    # Add users
    cmd1 = "modify group sztest_test_group --add-users sztest_user_a,sztest_user_b --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(result1, "Group 'sztest_test_group' modified successfully.", json=True)

    # Verify state after adding
    assert 'sztest_test_group' in get_system_user_details('sztest_user_a')
    assert 'sztest_test_group' in get_system_user_details('sztest_user_b')
    assert 'sztest_test_group' not in get_system_user_details('sztest_user_c')

    # Remove a user
    cmd2 = "modify group sztest_test_group --remove-users sztest_user_b --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Group 'sztest_test_group' modified successfully.", json=True)

    # Verify state after removing
    assert 'sztest_test_group' in get_system_user_details('sztest_user_a')
    assert 'sztest_test_group' not in get_system_user_details('sztest_user_b')
    assert 'sztest_test_group' not in get_system_user_details('sztest_user_c')


# --- Share Modification Tests ---

def test_modify_share_basic_properties(basic_users_and_groups: None) -> None:
    """Test modifying various properties of a share."""
    # Create share
    cmd1 = "create share modshare --dataset shares/modshare --pool primary_testpool --comment 'Original' --valid-users sztest_user_a --json"
    check_smb_zfs_result(run_smb_zfs_command(cmd1), "Share 'modshare' created successfully.", json=True)

    # Modify the share
    cmd2 = "modify share modshare --comment 'Modified' --valid-users sztest_user_a,sztest_user_b --readonly --quota 25G --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Share 'modshare' modified successfully.", json=True)

    # Verify application state
    final_state = run_smb_zfs_command("get-state")
    share_state = final_state['shares']['smb']['modshare']
    assert share_state['smb_config']['comment'] == 'Modified'
    assert 'sztest_user_b' in share_state['smb_config']['valid_users']
    assert share_state['smb_config']['read_only'] is True
    assert share_state['dataset']['quota'] == '25G'

    # Verify system state and smb.conf
    assert get_zfs_property('primary_testpool/shares/modshare', 'quota') == '25G'
    smb_conf = read_smb_conf()
    assert 'comment = Modified' in smb_conf
    assert 'valid users = sztest_user_a,sztest_user_b' in smb_conf
    assert 'read only = yes' in smb_conf


def test_modify_share_change_pool(basic_users_and_groups: None) -> None:
    """Test moving a share to a different pool."""
    # Create share
    cmd1 = "create share poolshare --dataset shares/poolshare --pool primary_testpool --json"
    check_smb_zfs_result(run_smb_zfs_command(cmd1), "Share 'poolshare' created successfully.", json=True)
    assert get_zfs_dataset_exists('primary_testpool/shares/poolshare')

    # Move share to secondary pool
    cmd2 = "modify share poolshare --pool secondary_testpool --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Share 'poolshare' modified successfully.", json=True)

    # Verify system state
    assert get_zfs_dataset_exists('secondary_testpool/shares/poolshare')
    assert not get_zfs_dataset_exists('primary_testpool/shares/poolshare')

    # Verify smb.conf path update
    smb_conf = read_smb_conf()
    assert 'path = /secondary_testpool/shares/poolshare' in smb_conf


def test_modify_share_permissions(basic_users_and_groups: None) -> None:
    """Test modifying share permissions and ownership."""
    # Create share
    cmd1 = "create share permshare --dataset shares/permshare --pool primary_testpool --json"
    check_smb_zfs_result(run_smb_zfs_command(cmd1), "Share 'permshare' created successfully.", json=True)
    share_path = get_zfs_property('primary_testpool/shares/permshare', 'mountpoint')
    
    # Check initial permissions
    assert get_file_permissions(share_path) == 775
    owner, group = get_owner_and_group(share_path)
    assert owner == 'root'
    assert group == 'smb_users'

    # Modify ownership and permissions
    cmd2 = "modify share permshare --owner sztest_user_a --group sztest_test_group --perms 750 --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Share 'permshare' modified successfully.", json=True)

    # Verify new permissions
    assert get_file_permissions(share_path) == 750
    owner, group = get_owner_and_group(share_path)
    assert owner == 'sztest_user_a'
    assert group == 'sztest_test_group'


def test_modify_share_browseable(basic_users_and_groups: None) -> None:
    """Test modifying share browseable setting."""
    # Create share (browseable by default)
    cmd1 = "create share browseshare --dataset shares/browseshare --pool primary_testpool --json"
    check_smb_zfs_result(run_smb_zfs_command(cmd1), "Share 'browseshare' created successfully.", json=True)
    assert 'browseable = yes' in read_smb_conf()

    # Make share non-browseable
    cmd2 = "modify share browseshare --no-browse --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Share 'browseshare' modified successfully.", json=True)

    # Verify state
    final_state = run_smb_zfs_command("get-state")
    assert final_state['shares']['smb']['browseshare']['smb_config']['browseable'] is False
    assert 'browseable = no' in read_smb_conf()


# --- Home Directory Modification Tests ---

def test_modify_home_quota_single_user(basic_users_and_groups: None) -> None:
    """Test modifying the quota of a user's home directory."""
    # Check initial quota (should be 'none' by default)
    home_dataset = 'primary_testpool/homes/sztest_user_a'
    assert get_zfs_property(home_dataset, 'quota') == 'none'

    # Modify the quota
    cmd1 = "modify home sztest_user_a --quota 5G --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(result1, "Quota for user 'sztest_user_a' has been set to 5G.", json=True)

    # Verify new quota
    assert get_zfs_property(home_dataset, 'quota') == '5G'
    final_state = run_smb_zfs_command("get-state")
    assert final_state['users']['sztest_user_a']['dataset']['quota'] == '5G'

    # Set it back to none
    cmd2 = "modify home sztest_user_a --quota none --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Quota for user 'sztest_user_a' has been set to none.", json=True)
    assert get_zfs_property(home_dataset, 'quota') == 'none'
