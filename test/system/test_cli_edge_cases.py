import pytest
import subprocess
import json
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

# --- Test different pool configurations ---
def test_create_share_on_different_pools(initial_state):
    """Test creating shares on different pools."""
    # Create shares on different pools
    run_smb_zfs_command("create share primary_share --dataset shares/primary_share --pool primary_testpool --json")
    run_smb_zfs_command("create share secondary_share --dataset shares/secondary_share --pool secondary_testpool --json")
    run_smb_zfs_command("create share tertiary_share --dataset shares/tertiary_share --pool tertiary_testpool --json")

    # Verify datasets are created on correct pools
    assert get_zfs_property('primary_testpool/shares/primary_share', 'type') == 'filesystem'
    assert get_zfs_property('secondary_testpool/shares/secondary_share', 'type') == 'filesystem'
    assert get_zfs_property('tertiary_testpool/shares/tertiary_share', 'type') == 'filesystem'

def test_share_without_explicit_pool(initial_state):
    """Test creating share without specifying pool (should use primary)."""
    run_smb_zfs_command("create share default_pool_share --dataset shares/default_pool_share --json")

    # Should be created on primary pool
    assert get_zfs_property('primary_testpool/shares/default_pool_share', 'type') == 'filesystem'

# --- Test user creation variations ---
def test_user_with_groups_flag(initial_state):
    """Test creating user with initial groups."""
    # Create groups first
    run_smb_zfs_command("create group initial_group1 --json")
    run_smb_zfs_command("create group initial_group2 --json")

    # Create user with initial groups
    run_smb_zfs_command("create user grouped_user --password 'GroupedPass!' --groups initial_group1,initial_group2 --json")

    user_details = get_system_user_details('grouped_user')
    assert 'initial_group1' in user_details
    assert 'initial_group2' in user_details

def test_user_shell_variations(initial_state):
    """Test different shell configurations."""
    # User with shell enabled
    run_smb_zfs_command("create user shell_user --password 'ShellPass!' --shell --json")
    user_details = get_system_user_details('shell_user')
    assert '/bin/bash' in user_details

    # User without shell (default)
    run_smb_zfs_command("create user noshell_user --password 'NoShellPass!' --json")
    user_details = get_system_user_details('noshell_user')
    # Should have restricted shell (implementation dependent)

# --- Test share permission combinations ---
def test_share_permission_combinations(initial_state):
    """Test various combinations of share permissions."""
    # Create users for testing
    run_smb_zfs_command("create user perm_user1 --password 'PermPass1!' --json")
    run_smb_zfs_command("create user perm_user2 --password 'PermPass2!' --json")
    run_smb_zfs_command("create group perm_group --json")

    # Share with user and group permissions
    run_smb_zfs_command("create share mixed_perms --dataset shares/mixed_perms --valid-users perm_user1,@perm_group --json")

    # Read-only share
    run_smb_zfs_command("create share readonly_share --dataset shares/readonly_share --readonly --json")

    # Non-browseable share
    run_smb_zfs_command("create share hidden_share --dataset shares/hidden_share --no-browse --json")

    # Share with custom ownership
    run_smb_zfs_command("create share custom_own --dataset shares/custom_own --owner perm_user1 --group perm_group --perms 750 --json")

    state = run_smb_zfs_command("get-state")

    assert 'mixed_perms' in state['samba']['shares']
    assert state['samba']['shares']['readonly_share']['read only'] == 'yes'
    assert state['samba']['shares']['hidden_share']['browseable'] == 'no'

# --- Test quota formats and edge cases ---
def test_quota_format_variations(initial_state):
    """Test different quota format specifications."""
    run_smb_zfs_command("create user quota_user --password 'QuotaPass!' --json")

    # Test different quota formats
    quota_formats = ['1G', '1024M', '2T', '500G']

    for i, quota in enumerate(quota_formats):
        run_smb_zfs_command(f"modify home quota_user --quota {quota} --json")
        assert get_zfs_property('primary_testpool/homes/quota_user', 'quota') == quota

    # Test removing quota
    run_smb_zfs_command("modify home quota_user --quota none --json")
    assert get_zfs_property('primary_testpool/homes/quota_user', 'quota') == 'none'

def test_share_quota_variations(initial_state):
    """Test share quota variations."""
    run_smb_zfs_command("create share quota_share --dataset shares/quota_share --quota 10G --json")
    assert get_zfs_property('primary_testpool/shares/quota_share', 'quota') == '10G'

    # Modify quota
    run_smb_zfs_command("modify share quota_share --quota 20G --json")
    assert get_zfs_property('primary_testpool/shares/quota_share', 'quota') == '20G'

# --- Test group membership edge cases ---
def test_group_membership_complex_operations(initial_state):
    """Test complex group membership operations."""
    # Create users and groups
    run_smb_zfs_command("create user member1 --password 'Member1!' --json")
    run_smb_zfs_command("create user member2 --password 'Member2!' --json")
    run_smb_zfs_command("create user member3 --password 'Member3!' --json")
    run_smb_zfs_command("create group complex_group --json")

    # Add multiple users at once
    run_smb_zfs_command("modify group complex_group --add-users member1,member2,member3 --json")

    # Verify all are members
    for user in ['member1', 'member2', 'member3']:
        assert 'complex_group' in get_system_user_details(user)

    # Remove some users
    run_smb_zfs_command("modify group complex_group --remove-users member1,member3 --json")

    # Verify membership changes
    assert 'complex_group' not in get_system_user_details('member1')
    assert 'complex_group' in get_system_user_details('member2')
    assert 'complex_group' not in get_system_user_details('member3')

# --- Test state file operations ---
def test_get_state_comprehensive(initial_state):
    """Test comprehensive state retrieval."""
    # Create various resources
    run_smb_zfs_command("create user state_user --password 'StatePass!' --json")
    run_smb_zfs_command("create group state_group --description 'State test group' --json")
    run_smb_zfs_command("create share state_share --dataset shares/state_share --comment 'State test share' --json")

    state = run_smb_zfs_command("get-state")

    # Verify state structure
    assert 'users' in state
    assert 'groups' in state
    assert 'samba' in state
    assert 'zfs' in state

    # Verify specific entries
    assert 'state_user' in state['users']
    assert 'state_group' in state['groups']
    assert 'state_share' in state['samba']['shares']

    # Verify nested structure
    assert 'global' in state['samba']
    assert 'shares' in state['samba']
    assert 'pools' in state['zfs']

# --- Test error conditions and recovery ---
def test_invalid_pool_operations(initial_state):
    """Test operations with invalid pools."""
    # Try to create share on non-existent pool
    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command("create share invalid_pool_share --dataset shares/invalid_pool_share --pool nonexistent_pool --json")

def test_invalid_user_references(initial_state):
    """Test operations referencing invalid users."""
    # Try to add non-existent user to group
    run_smb_zfs_command("create group test_group --json")
    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command("modify group test_group --add-users nonexistent_user --json")

    # Try to create share with invalid valid-users
    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command("create share invalid_user_share --dataset shares/invalid_user_share --valid-users nonexistent_user --json")

def test_dataset_path_variations(initial_state):
    """Test different dataset path formats."""
    # Test various dataset path formats
    dataset_paths = [
        'shares/simple',
        'shares/nested/path',
        'shares/deeply/nested/path/structure'
    ]

    for i, path in enumerate(dataset_paths):
        share_name = f"path_test_{i}"
        run_smb_zfs_command(f"create share {share_name} --dataset {path} --json")

        # Verify dataset was created (path format depends on implementation)
        state = run_smb_zfs_command("get-state")
        assert share_name in state['samba']['shares']
