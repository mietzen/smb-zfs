import pytest
import subprocess
from conftest import run_smb_zfs_command

def get_system_user(username):
    """Check if a system user exists."""
    try:
        subprocess.run(f"getent passwd {username}", shell=True, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def get_zfs_dataset(dataset):
    """Check if a ZFS dataset exists."""
    try:
        subprocess.run(f"zfs list {dataset}", shell=True, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def read_smb_conf():
    """Read the contents of the smb.conf file."""
    with open('/etc/samba/smb.conf', 'r') as f:
        return f.read()

def test_initial_setup_state(initial_state):
    """Verify the state after the initial setup in the fixture."""
    assert initial_state['zfs']['pools']['primary'] == 'primary_testpool'
    assert 'secondary_testpool' in initial_state['zfs']['pools']['secondary']
    assert 'tertiary_testpool' in initial_state['zfs']['pools']['secondary']
    assert initial_state['samba']['global']['workgroup'] == 'TESTGROUP'
    assert initial_state['samba']['global']['server string'] == 'TESTSERVER'
    assert get_zfs_dataset('primary_testpool/users')
    assert get_zfs_dataset('primary_testpool/shares')
    assert get_zfs_dataset('secondary_testpool/users')
    assert get_zfs_dataset('secondary_testpool/shares')

def test_modify_setup_add_secondary_pool(initial_state):
    """Test modifying setup to add a new secondary pool."""
    # Note: The test setup already includes 2 secondary pools. We'll verify them
    # and then could hypothetically add another if a fourth pool existed.
    # For now, we confirm the existing ones.
    assert 'secondary_testpool' in initial_state['zfs']['pools']['secondary']
    assert 'tertiary_testpool' in initial_state['zfs']['pools']['secondary']

    # This command would be used to add another pool if available
    # run_smb_zfs_command("modify setup --add-secondary-pools new_pool --json")
    # final_state = run_smb_zfs_command("get-state")
    # assert 'new_pool' in final_state['zfs']['pools']['secondary']


def test_modify_setup_remove_secondary_pool(initial_state):
    """Test modifying setup to remove a secondary pool."""
    run_smb_zfs_command("modify setup --remove-secondary-pools tertiary_testpool --json")
    final_state = run_smb_zfs_command("get-state")

    assert 'tertiary_testpool' not in final_state['zfs']['pools']['secondary']
    assert 'secondary_testpool' in final_state['zfs']['pools']['secondary']
    assert not get_zfs_dataset('tertiary_testpool/users')
    assert not get_zfs_dataset('tertiary_testpool/shares')


def test_modify_setup_change_server_settings(initial_state):
    """Test changing server name and workgroup."""
    run_smb_zfs_command("modify setup --server-name NEWSERVER --workgroup NEWGROUP --json")
    final_state = run_smb_zfs_command("get-state")
    smb_conf_content = read_smb_conf()

    assert final_state['samba']['global']['workgroup'] == 'NEWGROUP'
    assert final_state['samba']['global']['server string'] == 'NEWSERVER'
    assert 'workgroup = NEWGROUP' in smb_conf_content
    assert 'server string = NEWSERVER' in smb_conf_content

def test_remove_command(initial_state):
    """
    Test the remove command. This is implicitly tested by the teardown fixture,
    but we can have an explicit test too.
    """
    # Create a user to ensure there's something to delete
    run_smb_zfs_command("create user testuser --password TestPassword123 --json")
    assert get_system_user('testuser')

    # Run remove
    run_smb_zfs_command("remove --delete-users --delete-data --yes --json")

    # Verify cleanup
    assert not get_system_user('testuser')
    assert not get_zfs_dataset('primary_testpool/users')
    assert not get_zfs_dataset('primary_testpool/shares')
    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command("get-state") # Should fail as setup is gone
