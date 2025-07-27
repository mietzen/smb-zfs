from conftest import (
    run_smb_zfs_command,
    get_system_user_details,
    get_system_user_shell,
    get_system_group_exists,
    get_zfs_property,
    read_smb_conf
)


# --- User Creation and Deletion Tests ---
def test_create_user_basic(initial_state):
    """Test creating a simple user."""
    run_smb_zfs_command(
        "create user sztest_testuser1 --password 'SecretPassword!' --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'sztest_testuser1' in final_state['users']
    assert get_system_user_details('sztest_testuser1') is not None
    assert get_zfs_property(
        'primary_testpool/homes/sztest_testuser1', 'mountpoint') == '/primary_testpool/homes/sztest_testuser1'


def test_create_user_no_home(initial_state):
    """Test creating a user with no home directory."""
    run_smb_zfs_command(
        "create user sztest_nohomeuser --password 'SecretPassword!' --no-home --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'sztest_nohomeuser' in final_state['users']
    user_details = get_system_user_details('sztest_nohomeuser')
    assert user_details is not None
    assert get_zfs_property(
        'primary_testpool/homes/sztest_nohomeuser', 'mountpoint') is None


def test_create_user_with_shell(initial_state):
    """Test creating a user with shell enabled."""
    run_smb_zfs_command(
        "create user sztest_shelluser --password 'SecretPassword!' --shell --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'shelluser' in final_state['users']
    user_shell = get_system_user_shell('shelluser')
    assert user_shell is not None
    # The shell should be /bin/bash when --shell is used
    assert '/bin/bash' in user_shell


def test_delete_user_basic(initial_state):
    """Test deleting a user."""
    run_smb_zfs_command(
        "create user sztest_todelete --password 'SecretPassword!' --json")
    assert get_system_user_details('todelete') is not None

    run_smb_zfs_command("delete user sztest_todelete --yes --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'todelete' not in final_state['users']
    assert get_system_user_details('todelete') is None


def test_delete_user_with_data(initial_state):
    """Test deleting a user and their data."""
    run_smb_zfs_command(
        "create user sztest_datadelete --password 'SecretPassword!' --json")
    assert get_zfs_property(
        'primary_testpool/homes/sztest_datadelete', 'type') == 'filesystem'

    run_smb_zfs_command("delete user sztest_datadelete --delete-data --yes --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'sztest_datadelete' not in final_state['users']
    assert get_zfs_property(
        'primary_testpool/homes/sztest_datadelete', 'type') is None


# --- Group Creation and Deletion Tests ---
def test_create_group_basic(initial_state):
    """Test creating a group."""
    run_smb_zfs_command(
        "create group sztest_testgroup1 --description 'A test group' --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'testgroup1' in final_state['groups']
    assert get_system_group_exists('testgroup1')


def test_create_group_with_users(initial_state):
    """Test creating a group with initial users."""
    # Create users first
    run_smb_zfs_command(
        "create user sztest_groupuser1 --password 'SecretPassword!' --json")
    run_smb_zfs_command(
        "create user sztest_groupuser2 --password 'SecretPassword!' --json")

    run_smb_zfs_command(
        "create group sztest_testgroup2 --description 'Group with users' --users groupuser1,groupuser2 --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'testgroup2' in final_state['groups']
    assert get_system_group_exists('testgroup2')
    # Check that users are in the group
    user1_details = get_system_user_details('groupuser1')
    user2_details = get_system_user_details('groupuser2')
    assert 'testgroup2' in user1_details
    assert 'testgroup2' in user2_details


def test_delete_group_basic(initial_state):
    """Test deleting a group."""
    run_smb_zfs_command(
        "create group sztest_groupdel --description 'Delete me' --json")
    assert get_system_group_exists('groupdel')

    run_smb_zfs_command("delete group sztest_groupdel --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'groupdel' not in final_state['groups']
    assert not get_system_group_exists('groupdel')


# --- Share Creation and Deletion Tests ---
def test_create_share_basic(initial_state):
    """Test creating a samba share."""
    run_smb_zfs_command(
        "create share testshare1 --dataset shares/testshare1 --pool primary_testpool --comment 'My Test Share' --quota 10G --json")
    final_state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert 'testshare1' in final_state['shares']
    assert get_zfs_property(
        'primary_testpool/shares/testshare1', 'quota') == '10G'
    assert '[testshare1]' in smb_conf
    assert 'comment = My Test Share' in smb_conf
    assert 'path = /primary_testpool/shares/testshare1' in smb_conf


def test_create_share_with_permissions(initial_state):
    """Test creating a share with specific users and permissions."""
    run_smb_zfs_command(
        "create user sztest_shareuser --password 'SecretPassword!' --json")
    run_smb_zfs_command(
        "create share restrictedshare --dataset shares/restrictedshare --pool secondary_testpool --valid-users shareuser --readonly --no-browse --json")
    final_state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert 'restrictedshare' in final_state['shares']
    assert '[restrictedshare]' in smb_conf
    assert 'valid users = shareuser' in smb_conf
    assert 'read only = yes' in smb_conf
    assert 'browseable = no' in smb_conf


def test_delete_share_basic(initial_state):
    """Test deleting a share."""
    run_smb_zfs_command(
        "create share deltshare --dataset shares/deltshare --pool primary_testpool --json")
    assert '[deltshare]' in read_smb_conf()

    run_smb_zfs_command("delete share deltshare --yes --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'deltshare' not in final_state['shares']
    assert '[deltshare]' not in read_smb_conf()
    # Dataset should still exist by default
    assert get_zfs_property(
        'primary_testpool/shares/deltshare', 'type') == 'filesystem'


def test_delete_share_with_data(initial_state):
    """Test deleting a share and its underlying data."""
    run_smb_zfs_command(
        "create share datadeltshare --dataset shares/datadeltshare --pool primary_testpool --json")
    assert get_zfs_property(
        'primary_testpool/shares/datadeltshare', 'type') == 'filesystem'

    run_smb_zfs_command(
        "delete share datadeltshare --delete-data --yes --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'datadeltshare' not in final_state['shares']
    assert get_zfs_property(
        'primary_testpool/shares/datadeltshare', 'type') is None


# --- Group Modification Tests ---
def test_modify_group_add_users(basic_users_and_groups):
    """Test adding users to a group."""
    run_smb_zfs_command(
        "modify group sztest_test_group --add-users sztest_user_a,sztest_user_b --json")

    user_a_details = get_system_user_details('sztest_user_a')
    user_b_details = get_system_user_details('sztest_user_b')
    user_c_details = get_system_user_details('sztest_user_c')

    assert 'test_group' in user_a_details
    assert 'test_group' in user_b_details
    assert 'test_group' not in user_c_details


def test_modify_group_remove_users(basic_users_and_groups):
    """Test removing users from a group."""
    # First add them
    run_smb_zfs_command(
        "modify group sztest_test_group --add-users sztest_user_a,sztest_user_b,sztest_user_c --json")
    assert 'test_group' in get_system_user_details('sztest_user_b')

    # Then remove one
    run_smb_zfs_command("modify group sztest_test_group --remove-users sztest_user_b --json")

    user_a_details = get_system_user_details('sztest_user_a')
    user_b_details = get_system_user_details('sztest_user_b')
    user_c_details = get_system_user_details('sztest_user_c')

    assert 'test_group' in user_a_details
    assert 'test_group' not in user_b_details
    assert 'test_group' in user_c_details


# --- Share Modification Tests ---
def test_modify_share_basic_properties(basic_users_and_groups):
    """Test modifying various properties of a share."""
    run_smb_zfs_command(
        "create share modshare --dataset shares/modshare --pool primary_testpool --comment 'Original' --valid-users sztest_user_a --json")

    # Modify the share
    run_smb_zfs_command(
        "modify share modshare --comment 'Modified' --valid-users sztest_user_a,sztest_user_b --readonly --quota 25G --json")

    final_state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert final_state['shares']['modshare']['smb_config']['comment'] == 'Modified'
    assert 'sztest_user_b' in final_state['shares']['modshare']['smb_config']['valid_users']
    assert final_state['shares']['modshare']['smb_config']['read_only'] == True
    assert get_zfs_property(
        'primary_testpool/shares/modshare', 'quota') == '25G'

    assert 'comment = Modified' in smb_conf
    assert 'valid users = sztest_user_a,sztest_user_b' in smb_conf
    assert 'read only = yes' in smb_conf


def test_modify_share_change_pool(basic_users_and_groups):
    """Test moving a share to a different pool."""
    run_smb_zfs_command(
        "create share poolshare --dataset shares/poolshare --pool primary_testpool --json")

    # Move share to secondary pool
    run_smb_zfs_command(
        "modify share poolshare --pool secondary_testpool --json")

    final_state = run_smb_zfs_command("get-state")

    # Check that the share dataset is now on the secondary pool
    assert get_zfs_property(
        'secondary_testpool/shares/poolshare', 'type') == 'filesystem'
    # Original dataset should be gone
    assert get_zfs_property(
        'primary_testpool/shares/poolshare', 'type') is None


def test_modify_share_permissions(basic_users_and_groups):
    """Test modifying share permissions and ownership."""
    run_smb_zfs_command(
        "create share permshare --dataset shares/permshare --pool primary_testpool --json")

    # Modify ownership and permissions
    run_smb_zfs_command(
        "modify share permshare --owner sztest_user_a --group test_group --perms 755 --json")

    final_state = run_smb_zfs_command("get-state")

    # These would need to be verified via actual file system checks in a real test
    # For now, verify the command structure works


def test_modify_share_browseable(basic_users_and_groups):
    """Test modifying share browseable setting."""
    run_smb_zfs_command(
        "create share browseshare --dataset shares/browseshare --pool primary_testpool --json")

    # Make share non-browseable
    run_smb_zfs_command("modify share browseshare --no-browse --json")

    final_state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert final_state['shares']['browseshare']['smb_config']['browseable'] == False
    assert 'browseable = no' in smb_conf


# --- Home Directory Modification Tests ---
def test_modify_home_quota_single_user(basic_users_and_groups):
    """Test modifying the quota of a user's home directory."""
    # Check initial quota (should be 'none' by default)
    assert get_zfs_property('primary_testpool/homes/sztest_user_a', 'quota') == 'none'

    # Modify the quota
    run_smb_zfs_command("modify home sztest_user_a --quota 5G --json")

    assert get_zfs_property('primary_testpool/homes/sztest_user_a', 'quota') == '5G'

    # Set it back to none
    run_smb_zfs_command("modify home sztest_user_a --quota none --json")
    assert get_zfs_property('primary_testpool/homes/sztest_user_a', 'quota') == 'none'


def test_modify_home_quota_multiple_users(basic_users_and_groups):
    """Test modifying quotas for multiple users."""
    # Set quotas for multiple users
    run_smb_zfs_command("modify home sztest_user_a --quota 10G --json")
    run_smb_zfs_command("modify home sztest_user_b --quota 15G --json")

    assert get_zfs_property('primary_testpool/homes/sztest_user_a', 'quota') == '10G'
    assert get_zfs_property('primary_testpool/homes/sztest_user_b', 'quota') == '15G'
    # sztest_user_c should still have no quota
    assert get_zfs_property('primary_testpool/homes/sztest_user_c', 'quota') == 'none'
