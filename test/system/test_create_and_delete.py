import subprocess
from conftest import run_smb_zfs_command

def get_system_user_details(username):
    """Get details for a system user."""
    try:
        result = subprocess.run(f"id {username}", shell=True, check=True, capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError:
        return None

def get_system_group(groupname):
    """Check if a system group exists."""
    try:
        subprocess.run(f"getent group {groupname}", shell=True, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

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

# --- User Tests ---
def test_create_user(initial_state):
    """Test creating a simple user."""
    run_smb_zfs_command("create user testuser1 --password 'SecretPassword!' --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'testuser1' in final_state['users']
    assert get_system_user_details('testuser1') is not None
    assert get_zfs_property('primary_testpool/homes/testuser1', 'mountpoint') == '/home/testuser1'

def test_create_user_with_options(initial_state):
    """Test creating a user with a specific shell and no home."""
    run_smb_zfs_command("create user noshelluser --password 'SecretPassword!' --no-home --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'noshelluser' in final_state['users']
    user_details = get_system_user_details('noshelluser')
    assert user_details is not None
    assert get_zfs_property('primary_testpool/homes/noshelluser', 'mountpoint') is None

def test_create_user_with_shell(initial_state):
    """Test creating a user with shell enabled."""
    run_smb_zfs_command("create user shelluser --password 'SecretPassword!' --shell --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'shelluser' in final_state['users']
    user_details = get_system_user_details('shelluser')
    assert user_details is not None
    # The shell should be /bin/bash when --shell is used
    assert '/bin/bash' in user_details

def test_delete_user(initial_state):
    """Test deleting a user."""
    run_smb_zfs_command("create user todelete --password 'SecretPassword!' --json")
    assert get_system_user_details('todelete') is not None

    run_smb_zfs_command("delete user todelete --yes --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'todelete' not in final_state['users']
    assert get_system_user_details('todelete') is None

def test_delete_user_with_data(initial_state):
    """Test deleting a user and their data."""
    run_smb_zfs_command("create user datadelete --password 'SecretPassword!' --json")
    assert get_zfs_property('primary_testpool/homes/datadelete', 'type') == 'filesystem'

    run_smb_zfs_command("delete user datadelete --delete-data --yes --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'datadelete' not in final_state['users']
    assert get_zfs_property('primary_testpool/homes/datadelete', 'type') is None

# --- Group Tests ---
def test_create_group(initial_state):
    """Test creating a group."""
    run_smb_zfs_command("create group testgroup1 --description 'A test group' --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'testgroup1' in final_state['groups']
    assert get_system_group('testgroup1')

def test_create_group_with_users(initial_state):
    """Test creating a group with initial users."""
    # Create users first
    run_smb_zfs_command("create user groupuser1 --password 'SecretPassword!' --json")
    run_smb_zfs_command("create user groupuser2 --password 'SecretPassword!' --json")

    run_smb_zfs_command("create group testgroup2 --description 'Group with users' --users groupuser1,groupuser2 --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'testgroup2' in final_state['groups']
    assert get_system_group('testgroup2')
    # Check that users are in the group
    user1_details = get_system_user_details('groupuser1')
    user2_details = get_system_user_details('groupuser2')
    assert 'testgroup2' in user1_details
    assert 'testgroup2' in user2_details

def test_delete_group(initial_state):
    """Test deleting a group."""
    run_smb_zfs_command("create group groupdel --description 'Delete me' --json")
    assert get_system_group('groupdel')

    run_smb_zfs_command("delete group groupdel --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'groupdel' not in final_state['groups']
    assert not get_system_group('groupdel')

# --- Share Tests ---
def test_create_share(initial_state):
    """Test creating a samba share."""
    run_smb_zfs_command("create share testshare1 --dataset shares/testshare1 --pool primary_testpool --comment 'My Test Share' --quota 10G --json")
    final_state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert 'testshare1' in final_state['samba']['shares']
    assert get_zfs_property('primary_testpool/shares/testshare1', 'quota') == '10G'
    assert '[testshare1]' in smb_conf
    assert 'comment = My Test Share' in smb_conf
    assert 'path = /shares/testshare1' in smb_conf

def test_create_share_with_permissions(initial_state):
    """Test creating a share with specific users and permissions."""
    run_smb_zfs_command("create user shareuser --password 'SecretPassword!' --json")
    run_smb_zfs_command("create share restrictedshare --dataset shares/restrictedshare --pool secondary_testpool --valid-users shareuser --readonly --no-browse --json")
    final_state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert 'restrictedshare' in final_state['samba']['shares']
    assert '[restrictedshare]' in smb_conf
    assert 'valid users = shareuser' in smb_conf
    assert 'read only = yes' in smb_conf
    assert 'browseable = no' in smb_conf

def test_delete_share(initial_state):
    """Test deleting a share."""
    run_smb_zfs_command("create share deltshare --dataset shares/deltshare --pool primary_testpool --json")
    assert '[deltshare]' in read_smb_conf()

    run_smb_zfs_command("delete share deltshare --yes --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'deltshare' not in final_state['samba']['shares']
    assert '[deltshare]' not in read_smb_conf()
    # Dataset should still exist by default
    assert get_zfs_property('primary_testpool/shares/deltshare', 'type') == 'filesystem'

def test_delete_share_with_data(initial_state):
    """Test deleting a share and its underlying data."""
    run_smb_zfs_command("create share datadeltshare --dataset shares/datadeltshare --pool primary_testpool --json")
    assert get_zfs_property('primary_testpool/shares/datadeltshare', 'type') == 'filesystem'

    run_smb_zfs_command("delete share datadeltshare --delete-data --yes --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'datadeltshare' not in final_state['samba']['shares']
    assert get_zfs_property('primary_testpool/shares/datadeltshare', 'type') is None
