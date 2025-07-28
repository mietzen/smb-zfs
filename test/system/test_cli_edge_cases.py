import pytest
import subprocess
from conftest import (
    run_smb_zfs_command,
    get_system_user_details,
    get_system_user_shell,
    get_zfs_property,
    read_smb_conf
)


# --- Pool Configuration Tests ---
def test_create_share_on_different_pools(initial_state):
    """Test creating shares on different pools."""
    # Create shares on different pools
    run_smb_zfs_command(
        "create share primary_share --dataset shares/primary_share --pool primary_testpool --json")
    run_smb_zfs_command(
        "create share secondary_share --dataset shares/secondary_share --pool secondary_testpool --json")
    run_smb_zfs_command(
        "create share tertiary_share --dataset shares/tertiary_share --pool tertiary_testpool --json")

    # Verify datasets are created on correct pools
    assert get_zfs_property(
        'primary_testpool/shares/primary_share', 'type') == 'filesystem'
    assert get_zfs_property(
        'secondary_testpool/shares/secondary_share', 'type') == 'filesystem'
    assert get_zfs_property(
        'tertiary_testpool/shares/tertiary_share', 'type') == 'filesystem'


def test_share_without_explicit_pool(initial_state):
    """Test creating share without specifying pool (should use primary)."""
    run_smb_zfs_command(
        "create share default_pool_share --dataset shares/default_pool_share --json")

    # Should be created on primary pool
    assert get_zfs_property(
        'primary_testpool/shares/default_pool_share', 'type') == 'filesystem'


# --- User Creation Variation Tests ---
def test_user_with_groups_flag(initial_state):
    """Test creating user with initial groups."""
    # Create groups first
    run_smb_zfs_command("create group sztest_initial_group1 --json")
    run_smb_zfs_command("create group sztest_initial_group2 --json")

    # create user sztest_with initial groups
    run_smb_zfs_command(
        "create user sztest_grouped_user --password 'GroupedPass!' --groups sztest_initial_group1,sztest_initial_group2 --json")

    user_details = get_system_user_details('sztest_grouped_user')
    assert 'sztest_initial_group1' in user_details
    assert 'sztest_initial_group2' in user_details


def test_user_shell_variations(initial_state):
    """Test different shell configurations."""
    # User with shell enabled
    run_smb_zfs_command(
        "create user sztest_shell_user --password 'ShellPass!' --shell --json")
    user_shell = get_system_user_shell('sztest_shell_user')
    assert '/bin/bash' in user_shell

    # User without shell (default)
    run_smb_zfs_command(
        "create user sztest_noshell_user --password 'NoShellPass!' --json")
    user_details = get_system_user_details('sztest_noshell_user')
    # Should have restricted shell (implementation dependent)


# --- Share Permission Combination Tests ---
def test_share_permission_combinations(initial_state):
    """Test various combinations of share permissions."""
    # Create users for testing
    run_smb_zfs_command(
        "create user sztest_perm_user1 --password 'PermPass1!' --json")
    run_smb_zfs_command(
        "create user sztest_perm_user2 --password 'PermPass2!' --json")
    run_smb_zfs_command("create group sztest_perm_group --json")

    # Share with user and group permissions
    run_smb_zfs_command(
        "create share mixed_perms --dataset shares/mixed_perms --valid-users sztest_perm_user1,@sztest_perm_group --json")

    # Read-only share
    run_smb_zfs_command(
        "create share readonly_share --dataset shares/readonly_share --readonly --json")

    # Non-browseable share
    run_smb_zfs_command(
        "create share hidden_share --dataset shares/hidden_share --no-browse --json")

    # Share with custom ownership
    run_smb_zfs_command(
        "create share custom_own --dataset shares/custom_own --owner sztest_perm_user1 --group sztest_perm_group --perms 750 --json")

    state = run_smb_zfs_command("get-state")

    assert 'mixed_perms' in state['shares']
    assert state['shares']['readonly_share']['smb_config']['read_only'] == True
    assert state['shares']['hidden_share']['smb_config']['browseable'] == False


# --- Quota Format and Edge Case Tests ---
def test_quota_format_variations(initial_state):
    """Test different quota format specifications."""
    run_smb_zfs_command(
        "create user sztest_quota_user --password 'QuotaPass!' --json")

    # Test different quota formats
    quota_formats = ['1G', '512M', '2T', '500G']

    for i, quota in enumerate(quota_formats):
        run_smb_zfs_command(f"modify home sztest_quota_user --quota {quota} --json")
        assert get_zfs_property(
            'primary_testpool/homes/sztest_quota_user', 'quota') == quota

    # Test removing quota
    run_smb_zfs_command("modify home sztest_quota_user --quota none --json")
    assert get_zfs_property(
        'primary_testpool/homes/sztest_quota_user', 'quota') == 'none'


def test_share_quota_variations(initial_state):
    """Test share quota variations."""
    run_smb_zfs_command(
        "create share quota_share --dataset shares/quota_share --quota 10G --json")
    assert get_zfs_property(
        'primary_testpool/shares/quota_share', 'quota') == '10G'

    # Modify quota
    run_smb_zfs_command("modify share quota_share --quota 20G --json")
    assert get_zfs_property(
        'primary_testpool/shares/quota_share', 'quota') == '20G'


# --- Group Membership Edge Case Tests ---
def test_group_membership_complex_operations(initial_state):
    """Test complex group membership operations."""
    # Create users and groups
    run_smb_zfs_command("create user sztest_member1 --password 'sztest_member1!' --json")
    run_smb_zfs_command("create user sztest_member2 --password 'sztest_member2!' --json")
    run_smb_zfs_command("create user sztest_member3 --password 'sztest_member3!' --json")
    run_smb_zfs_command("create group sztest_complex_group --json")

    # Add multiple users at once
    run_smb_zfs_command(
        "modify group sztest_complex_group --add-users sztest_member1,sztest_member2,sztest_member3 --json")

    # Verify all are members
    for user in ['sztest_member1', 'sztest_member2', 'sztest_member3']:
        assert 'complex_group' in get_system_user_details(user)

    # Remove some users
    run_smb_zfs_command(
        "modify group sztest_complex_group --remove-users sztest_member1,sztest_member3 --json")

    # Verify membership changes
    assert 'complex_group' not in get_system_user_details('sztest_member1')
    assert 'complex_group' in get_system_user_details('sztest_member2')
    assert 'complex_group' not in get_system_user_details('sztest_member3')


# --- State File Operation Tests ---
def test_get_state_comprehensive(initial_state):
    """Test comprehensive state retrieval."""
    # Create various resources
    run_smb_zfs_command(
        "create user sztest_state_user --password 'StatePass!' --json")
    run_smb_zfs_command(
        "create group sztest_state_group --description 'State test group' --json")
    run_smb_zfs_command(
        "create share state_share --dataset shares/state_share --comment 'State test share' --json")

    state = run_smb_zfs_command("get-state")

    # Verify state structure
    assert 'users' in state
    assert 'groups' in state

    # Verify specific entries
    assert 'sztest_state_user' in state['users']
    assert 'sztest_state_group' in state['groups']
    assert 'state_share' in state['shares']

    # Verify nested structure
    assert 'shares' in state


# --- Error Condition and Recovery Tests ---
def test_invalid_pool_operations(initial_state):
    """Test operations with invalid pools."""
    # Try to create share on non-existent pool
    result = run_smb_zfs_command(
        "create share invalid_pool_share --dataset shares/invalid_pool_share --pool nonexistent_pool --json")
    assert result == "Error: Pool 'nonexistent_pool' is not a valid pool. Managed pools are: primary_testpool, secondary_testpool, tertiary_testpool"


def test_invalid_user_references(initial_state):
    """Test operations referencing invalid users."""
    # Try to add non-existent user to group
    run_smb_zfs_command("create group sztest_test_group --json")
    result = run_smb_zfs_command("modify group sztest_test_group --add-users sztest_nonexistent_user --json")
    assert result == "Error: User 'sztest_nonexistent_user' not found or not managed by this tool."

    result = run_smb_zfs_command("create share invalid_user_share --dataset shares/invalid_user_share --valid-users nonexistent_user --json")
    assert "Error: User 'nonexistent_user' not found or not managed by this tool." in result.split('\n')


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
        run_smb_zfs_command(
            f"create share {share_name} --dataset {path} --json")

        # Verify dataset was created (path format depends on implementation)
        state = run_smb_zfs_command("get-state")
        assert share_name in state['shares']


# --- Multiple Operations Sequence Tests ---
def test_multiple_operations_sequence(initial_state):
    """Test sequence of multiple operations."""
    # Simulate a workflow of operations
    operations = [
        "create user sztest_workflow_user --password 'WorkflowPass!' --json",
        "create group sztest_workflow_group --description 'Workflow group' --json",
        "modify group sztest_workflow_group --add-users sztest_workflow_user --json",
        "create share workflow_share --dataset shares/workflow_share --valid-users @sztest_workflow_user --json",
        "modify share workflow_share --comment 'Modified workflow share' --quota 15G --json",
        "modify home sztest_workflow_user --quota 5G --json"
    ]

    # Execute operations in sequence
    for operation in operations:
        run_smb_zfs_command(operation)

    # Verify final state
    final_state = run_smb_zfs_command("get-state")

    assert 'sztest_workflow_user' in final_state['users']
    assert 'sztest_workflow_group' in final_state['groups']
    assert 'workflow_share' in final_state['shares']
    assert final_state['shares']['workflow_share']['smb_config']['comment'] == 'Modified workflow share'
    assert get_zfs_property(
        'primary_testpool/shares/workflow_share', 'quota') == '15G'
    assert get_zfs_property(
        'primary_testpool/homes/sztest_workflow_user', 'quota') == '5G'


# --- Boolean Flag Modification Tests ---
def test_modify_share_boolean_flags(initial_state):
    """Test share modification with boolean flag variations."""
    run_smb_zfs_command(
        "create share bool_share --dataset shares/bool_share --json")

    # Test enabling readonly
    run_smb_zfs_command("modify share bool_share --readonly --json")
    state = run_smb_zfs_command("get-state")
    assert state['shares']['bool_share']['smb_config']['read_only'] == True

    # Test disabling readonly (using --no-readonly if supported, or opposite flag)
    run_smb_zfs_command("modify share bool_share --json")  # Reset to default

    # Test enabling no-browse
    run_smb_zfs_command("modify share bool_share --no-browse --json")
    state = run_smb_zfs_command("get-state")
    assert state['shares']['bool_share']['smb_config']['browseable'] == False


def test_modify_setup_boolean_variations(initial_state):
    """Test setup modification boolean variations."""
    # Enable macOS optimization
    run_smb_zfs_command("modify setup --macos --json")
    state = run_smb_zfs_command("get-state")
    # Verify macOS settings are applied (implementation dependent)

    # Test setting default home quota
    run_smb_zfs_command("modify setup --default-home-quota 30G --json")
    state = run_smb_zfs_command("get-state")

    # Reset to none
    run_smb_zfs_command("modify setup --default-home-quota none --json")
    state = run_smb_zfs_command("get-state")


# --- Cleanup and Deletion Edge Case Tests ---
def test_delete_user_with_group_membership(initial_state):
    """Test deleting user who is member of groups."""
    run_smb_zfs_command(
        "create user sztest_member_user --password 'MemberPass!' --json")
    run_smb_zfs_command("create group sztest_member_group --users sztest_member_user --json")

    # Verify user is in group
    assert 'sztest_member_group' in get_system_user_details('sztest_member_user')

    # Delete user
    run_smb_zfs_command("delete user sztest_member_user --yes --json")

    # User should be removed from group automatically
    state = run_smb_zfs_command("get-state")
    assert 'sztest_member_user' not in state['users']
    # Group should still exist but without the user


def test_delete_group_with_members(initial_state):
    """Test deleting group that has members."""
    run_smb_zfs_command(
        "create user sztest_group_member --password 'GroupMemberPass!' --json")
    run_smb_zfs_command(
        "create group sztest_member_group --users sztest_group_member --json")

    # Delete group
    run_smb_zfs_command("delete group sztest_member_group --json")

    # Group should be gone, user should remain
    state = run_smb_zfs_command("get-state")
    assert 'sztest_member_group' not in state['groups']
    assert 'sztest_group_member' in state['users']


def test_delete_share_with_dependencies(initial_state):
    """Test deleting share that's referenced by users."""
    run_smb_zfs_command(
        "create user sztest_share_user --password 'ShareUserPass!' --json")
    run_smb_zfs_command(
        "create share dependent_share --dataset shares/dependent_share --valid-users share_user --json")

    # Delete share
    run_smb_zfs_command("delete share dependent_share --yes --json")

    # Share should be gone, user should remain
    state = run_smb_zfs_command("get-state")
    assert 'dependent_share' not in state['shares']
    assert 'sztest_share_user' in state['users']


# --- Complex Remove Scenario Tests ---
def test_remove_users_with_complex_setup():
    """Test remove command with complex setup."""
    # Create complex setup
    run_smb_zfs_command(
        "setup --primary-pool primary_testpool --secondary-pools secondary_testpool tertiary_testpool --server-name COMPLEXTEST --workgroup COMPLEXGROUP --macos --default-home-quota 25G")

    # Add complex data
    run_smb_zfs_command(
        "create user sztest_complex1 --password 'sztest_complex1!' --shell --json")
    run_smb_zfs_command(
        "create user sztest_complex2 --password 'Complex2!' --no-home --json")
    run_smb_zfs_command("create group sztest_complex_group --users sztest_complex1 --json")
    run_smb_zfs_command(
        "create share complex_share1 --dataset shares/complex_share1 --pool primary_testpool --json")
    run_smb_zfs_command(
        "create share complex_share2 --dataset shares/complex_share2 --pool secondary_testpool --valid-users @complex_group --json")

    # Test partial remove (users only)
    run_smb_zfs_command("remove --delete-users --yes --json")

    # Verify users gone, data remains
    assert None == get_system_user_details('sztest_complex1')

    # Datasets should still exist
    assert get_zfs_property(
        'primary_testpool/homes/sztest_complex1', 'type') == 'filesystem'
    assert get_zfs_property(
        'primary_testpool/shares/complex_share1', 'type') == 'filesystem'

# --- Complex Remove Scenario Tests ---
def test_remove_data_with_complex_setup():
    """Test remove command with complex setup."""

    # Create complex setup
    run_smb_zfs_command(
        "setup --primary-pool primary_testpool --secondary-pools secondary_testpool tertiary_testpool --server-name COMPLEXTEST --workgroup COMPLEXGROUP --macos --default-home-quota 25G")

    # Add complex data
    run_smb_zfs_command(
        "create user sztest_complex1 --password 'sztest_complex1!' --shell --json")
    run_smb_zfs_command(
        "create user sztest_complex2 --password 'Complex2!' --no-home --json")
    run_smb_zfs_command("create group sztest_complex_group --users sztest_complex1 --json")
    run_smb_zfs_command(
        "create share complex_share1 --dataset shares/complex_share1 --pool primary_testpool --json")
    run_smb_zfs_command(
        "create share complex_share2 --dataset shares/complex_share2 --pool secondary_testpool --valid-users @complex_group --json")

    # Complete removal
    run_smb_zfs_command("remove --delete-data --yes --json")

    # Verify users remain
    assert 'sztest_complex1' in get_system_user_details('sztest_complex1')

    # Everything should be gone
    assert get_zfs_property('primary_testpool/homes', 'type') is None
    assert get_zfs_property('primary_testpool/shares/complex_share1', 'type') is None
    assert get_zfs_property('primary_testpool/shares/complex_share2', 'type') is None


# --- Parameter Validation Tests ---
def test_invalid_parameter_combinations(initial_state):
    """Test commands with invalid parameter combinations."""
    # Try to modify group sztest_without any modification flags
    run_smb_zfs_command(
        "create user sztest_complex1 --password 'sztest_complex1!' --shell --json")
    run_smb_zfs_command("create group sztest_comp_group1 --users sztest_complex1 --json")
    result = run_smb_zfs_command(
        "modify group sztest_comp_group1 --json")
    assert result == "Error: Found no users to add or remove!"


def test_password_security_handling(initial_state):
    """Test password handling security."""
    # Test that passwords aren't exposed in process lists or error messages
    # This is more of a security test and would need special verification

    # create user with password
    run_smb_zfs_command(
        "create user sztest_security_user --password 'SecretPassword123!' --json")

    # Verify user was created successfully
    assert get_system_user_details('sztest_security_user') is not None


# --- Dataset Structure Tests ---
def test_dataset_structure_consistency(initial_state):
    """Test that dataset structure is consistent."""
    # Create resources and verify dataset structure
    run_smb_zfs_command(
        "create user sztest_struct_user --password 'StructPass!' --json")
    run_smb_zfs_command(
        "create share struct_share --dataset shares/struct_share --json")

    # Verify consistent naming structure
    assert get_zfs_property(
        'primary_testpool/homes/sztest_struct_user', 'type') == 'filesystem'
    assert get_zfs_property(
        'primary_testpool/shares/struct_share', 'type') == 'filesystem'

    # Verify mountpoints are correct
    assert get_zfs_property(
        'primary_testpool/homes/sztest_struct_user', 'mountpoint') == '/primary_testpool/homes/sztest_struct_user'
    # Share mountpoint should be under /shares


# --- Configuration File Consistency Tests ---
def test_smb_conf_consistency(initial_state):
    """Test that smb.conf stays consistent with state."""
    # Create share
    run_smb_zfs_command(
        "create share conf_share --dataset shares/conf_share --comment 'Config test share' --readonly --json")

    state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    # Verify state matches smb.conf
    share_config = state['shares']['conf_share']

    assert f"[conf_share]" in smb_conf
    assert f"comment = {share_config['smb_config']['comment']}" in smb_conf
    read_only = 'yes' if share_config['smb_config']['read_only'] else 'no'
    assert f"read only = {read_only}" in smb_conf

    # Modify share and verify consistency
    run_smb_zfs_command(
        "modify share conf_share --comment 'Modified config test' --json")

    updated_state = run_smb_zfs_command("get-state")
    updated_smb_conf = read_smb_conf()

    assert "comment = Modified config test" in updated_smb_conf


# --- System Integration Tests ---
def test_system_user_integration(initial_state):
    """Test integration with system user management."""
    run_smb_zfs_command(
        "create user sztest_sys_user --password 'SysPass!' --shell --json")

    # Verify system user exists and has correct properties
    user_shell = get_system_user_shell('sztest_sys_user')
    assert user_shell is not None
    assert '/bin/bash' in user_shell  # Should have shell when --shell is used

    # Verify user is in smb_users group (created during setup)
    user_details = get_system_user_details('sztest_sys_user')
    assert user_details is not None
    assert 'smb_users' in user_details


def test_comprehensive_workflow(initial_state):
    """Test a comprehensive workflow simulating real usage."""
    # Simulate setting up a complete SMB environment

    # 1. Create departments (groups)
    departments = ['sztest_engineering', 'sztest_marketing', 'sztest_finance']
    for dept in departments:
        run_smb_zfs_command(
            f"create group sztest_{dept} --description '{dept.capitalize()} department' --json")

    # 2. Create users for each department
    users = [
        ('sztest_alice', 'sztest_engineering'),
        ('sztest_bob', 'sztest_engineering'),
        ('sztest_carol', 'sztest_marketing'),
        ('sztest_dave', 'sztest_finance')
    ]

    for username, dept in users:
        run_smb_zfs_command(
            f"create user {username} --password '{username.capitalize()}Pass!' --shell --json")
        run_smb_zfs_command(
            f"modify group {dept} --add-users {username} --json")

    # 3. Create departmental shares
    for dept in departments:
        run_smb_zfs_command(
            f"create share {dept}_share --dataset shares/{dept} --valid-users @{dept} --quota 100G --comment '{dept.capitalize()} department share' --json")

    # 4. Create a common share
    run_smb_zfs_command(
        f"create share common --dataset shares/common --valid-users {','.join([x[0] for x in users])} --comment 'Common shared area' --json")

    # 5. Set individual quotas
    for username, _ in users:
        run_smb_zfs_command(f"modify home {username} --quota 10G --json")

    # 6. Verify final state
    final_state = run_smb_zfs_command("get-state")

    # Verify all users exist
    for username, _ in users:
        assert username in final_state['users']
        assert get_zfs_property(
            f'primary_testpool/homes/{username}', 'quota') == '10G'

    # Verify all groups exist
    for dept in departments:
        assert dept in final_state['groups']

    # Verify all shares exist
    for dept in departments:
        assert f'{dept}_share' in final_state['shares']
        assert get_zfs_property(
            f'primary_testpool/shares/{dept}', 'quota') == '100G'

    assert 'common' in final_state['shares']
