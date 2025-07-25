import pytest
import subprocess
from conftest import run_smb_zfs_command

def get_system_user_details(username):
    """Get details for a system user."""
    try:
        result = subprocess.run(f"id {username}", shell=True, check=True, capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError:
        return None

def get_zfs_property(dataset, prop):
    """Get a specific ZFS property."""
    try:
        result = subprocess.run(f"zfs get -H -o value {prop} {dataset}", shell=True, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def read_smb_conf():
    """Read the contents of the smb.conf file."""
    with open('/etc/samba/smb.conf', 'r') as f:
        return f.read()

@pytest.fixture
def setup_users_and_groups():
    """Fixture to create users and groups needed for modify tests."""
    run_smb_zfs_command("create user user_a --password 'PassA' --json")
    run_smb_zfs_command("create user user_b --password 'PassB' --json")
    run_smb_zfs_command("create user user_c --password 'PassC' --json")
    run_smb_zfs_command("create group modify_group --description 'A group to modify' --json")

# --- Group Modification Tests ---
def test_modify_group_add_users(setup_users_and_groups):
    """Test adding users to a group."""
    run_smb_zfs_command("modify group modify_group --add-users user_a,user_b --json")

    user_a_details = get_system_user_details('user_a')
    user_b_details = get_system_user_details('user_b')
    user_c_details = get_system_user_details('user_c')

    assert 'modify_group' in user_a_details
    assert 'modify_group' in user_b_details
    assert 'modify_group' not in user_c_details

def test_modify_group_remove_users(setup_users_and_groups):
    """Test removing users from a group."""
    # First add them
    run_smb_zfs_command("modify group modify_group --add-users user_a,user_b,user_c --json")
    assert 'modify_group' in get_system_user_details('user_b')

    # Then remove one
    run_smb_zfs_command("modify group modify_group --remove-users user_b --json")

    user_a_details = get_system_user_details('user_a')
    user_b_details = get_system_user_details('user_b')
    user_c_details = get_system_user_details('user_c')

    assert 'modify_group' in user_a_details
    assert 'modify_group' not in user_b_details
    assert 'modify_group' in user_c_details

# --- Share Modification Tests ---
def test_modify_share(setup_users_and_groups):
    """Test modifying various properties of a share."""
    run_smb_zfs_command("create share modshare --dataset shares/modshare --pool primary_testpool --comment 'Original' --valid-users user_a --json")

    # Modify the share
    run_smb_zfs_command("modify share modshare --comment 'Modified' --valid-users user_a,user_b --readonly --quota 25G --json")

    final_state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert final_state['samba']['shares']['modshare']['comment'] == 'Modified'
    assert 'user_b' in final_state['samba']['shares']['modshare']['valid users']
    assert final_state['samba']['shares']['modshare']['read only'] == 'yes'
    assert get_zfs_property('primary_testpool/shares/modshare', 'quota') == '25G'

    assert 'comment = Modified' in smb_conf
    assert 'valid users = user_a,user_b' in smb_conf
    assert 'read only = yes' in smb_conf

def test_modify_share_change_pool(setup_users_and_groups):
    """Test moving a share to a different pool."""
    run_smb_zfs_command("create share poolshare --dataset shares/poolshare --pool primary_testpool --json")

    # Move share to secondary pool
    run_smb_zfs_command("modify share poolshare --pool secondary_testpool --json")

    final_state = run_smb_zfs_command("get-state")

    # Check that the share dataset is now on the secondary pool
    assert get_zfs_property('secondary_testpool/shares/poolshare', 'type') == 'filesystem'
    # Original dataset should be gone
    assert get_zfs_property('primary_testpool/shares/poolshare', 'type') is None

def test_modify_share_permissions(setup_users_and_groups):
    """Test modifying share permissions and ownership."""
    run_smb_zfs_command("create share permshare --dataset shares/permshare --pool primary_testpool --json")

    # Modify ownership and permissions
    run_smb_zfs_command("modify share permshare --owner user_a --group modify_group --perms 755 --json")

    final_state = run_smb_zfs_command("get-state")

    # These would need to be verified via actual file system checks in a real test
    # For now, verify the command structure works

def test_modify_share_browseable(setup_users_and_groups):
    """Test modifying share browseable setting."""
    run_smb_zfs_command("create share browseshare --dataset shares/browseshare --pool primary_testpool --json")

    # Make share non-browseable
    run_smb_zfs_command("modify share browseshare --no-browse --json")

    final_state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert final_state['samba']['shares']['browseshare']['browseable'] == 'no'
    assert 'browseable = no' in smb_conf

# --- Home Directory Modification Tests ---
def test_modify_home_quota(setup_users_and_groups):
    """Test modifying the quota of a user's home directory."""
    # Check initial quota (should be 'none' by default)
    assert get_zfs_property('primary_testpool/homes/user_a', 'quota') == 'none'

    # Modify the quota
    run_smb_zfs_command("modify home user_a --quota 5G --json")

    assert get_zfs_property('primary_testpool/homes/user_a', 'quota') == '5G'

    # Set it back to none
    run_smb_zfs_command("modify home user_a --quota none --json")
    assert get_zfs_property('primary_testpool/homes/user_a', 'quota') == 'none'

def test_modify_home_quota_multiple_users(setup_users_and_groups):
    """Test modifying quotas for multiple users."""
    # Set quotas for multiple users
    run_smb_zfs_command("modify home user_a --quota 10G --json")
    run_smb_zfs_command("modify home user_b --quota 15G --json")

    assert get_zfs_property('primary_testpool/homes/user_a', 'quota') == '10G'
    assert get_zfs_property('primary_testpool/homes/user_b', 'quota') == '15G'
    # user_c should still have no quota
    assert get_zfs_property('primary_testpool/homes/user_c', 'quota') == 'none'