from conftest import (
    run_smb_zfs_command,
    check_smb_zfs_result,
    get_system_user_details,
    get_system_user_shell,
    get_system_group_exists,
    get_file_permissions,
    get_owner_and_group,
    get_zfs_property,
    read_smb_conf
)


# --- Pool Configuration Tests ---
def test_create_share_on_different_pools(initial_state) -> None:
    """Test creating shares on different pools."""
    # Create share on primary pool
    cmd = "create share primary_share --dataset shares/primary_share --pool primary_testpool --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'primary_share' created successfully.", json=True)

    # Create share on secondary pool
    cmd = "create share secondary_share --dataset shares/secondary_share --pool secondary_testpool --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'secondary_share' created successfully.", json=True)

    # Create share on tertiary pool
    cmd = "create share tertiary_share --dataset shares/tertiary_share --pool tertiary_testpool --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'tertiary_share' created successfully.", json=True)

    # Verify state
    state = run_smb_zfs_command("get-state")
    assert 'primary_share' in state['shares']
    assert 'secondary_share' in state['shares']
    assert 'tertiary_share' in state['shares']

    # Verify ZFS datasets are created on correct pools
    assert get_zfs_property(
        'primary_testpool/shares/primary_share', 'type') == 'filesystem'
    assert get_zfs_property(
        'secondary_testpool/shares/secondary_share', 'type') == 'filesystem'
    assert get_zfs_property(
        'tertiary_testpool/shares/tertiary_share', 'type') == 'filesystem'

    # Verify smb.conf entries
    smb_conf = read_smb_conf()
    assert '[primary_share]' in smb_conf
    assert '[secondary_share]' in smb_conf
    assert '[tertiary_share]' in smb_conf
    assert 'path = /primary_testpool/shares/primary_share' in smb_conf
    assert 'path = /secondary_testpool/shares/secondary_share' in smb_conf
    assert 'path = /tertiary_testpool/shares/tertiary_share' in smb_conf


def test_share_without_explicit_pool(initial_state) -> None:
    """Test creating share without specifying pool (should use primary)."""
    cmd = "create share default_pool_share --dataset shares/default_pool_share --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'default_pool_share' created successfully.", json=True)

    # Verify state
    state = run_smb_zfs_command("get-state")
    assert 'default_pool_share' in state['shares']

    # Should be created on primary pool by default
    assert get_zfs_property(
        'primary_testpool/shares/default_pool_share', 'type') == 'filesystem'

    # Verify smb.conf
    smb_conf = read_smb_conf()
    assert '[default_pool_share]' in smb_conf
    assert 'path = /primary_testpool/shares/default_pool_share' in smb_conf


# --- User Creation Variation Tests ---
def test_user_with_groups_flag(initial_state) -> None:
    """Test creating user with initial groups."""
    # Create groups first
    cmd = "create group sztest_initial_group1 --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_initial_group1' created successfully.", json=True)

    cmd = "create group sztest_initial_group2 --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_initial_group2' created successfully.", json=True)

    # Create user with initial groups
    cmd = "create user sztest_grouped_user --password 'GroupedPass!' --groups sztest_initial_group1,sztest_initial_group2 --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_grouped_user' created successfully.", json=True)

    # Verify state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_grouped_user' in state['users']
    assert 'sztest_initial_group1' in state['groups']
    assert 'sztest_initial_group2' in state['groups']

    # Verify system user details
    user_details = get_system_user_details('sztest_grouped_user')
    assert user_details is not None
    assert 'sztest_initial_group1' in user_details
    assert 'sztest_initial_group2' in user_details

    # Verify ZFS home directory
    assert get_zfs_property('primary_testpool/homes/sztest_grouped_user',
                            'mountpoint') == '/primary_testpool/homes/sztest_grouped_user'


def test_user_shell_variations(initial_state) -> None:
    """Test different shell configurations."""
    # User with shell enabled
    cmd = "create user sztest_shell_user --password 'ShellPass!' --shell --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_shell_user' created successfully.", json=True)

    # User without shell (default)
    cmd = "create user sztest_noshell_user --password 'NoShellPass!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_noshell_user' created successfully.", json=True)

    # Verify state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_shell_user' in state['users']
    assert 'sztest_noshell_user' in state['users']

    # Verify system user details
    shell_user_details = get_system_user_details('sztest_shell_user')
    noshell_user_details = get_system_user_details('sztest_noshell_user')
    assert shell_user_details is not None
    assert noshell_user_details is not None

    # Verify shell configuration
    shell_user_shell = get_system_user_shell('sztest_shell_user')
    noshell_user_shell = get_system_user_shell('sztest_noshell_user')
    assert '/bin/bash' in shell_user_shell
    # No shell user should have restricted shell
    assert shell_user_shell != noshell_user_shell

    # Verify ZFS home directories
    assert get_zfs_property('primary_testpool/homes/sztest_shell_user',
                            'mountpoint') == '/primary_testpool/homes/sztest_shell_user'
    assert get_zfs_property('primary_testpool/homes/sztest_noshell_user',
                            'mountpoint') == '/primary_testpool/homes/sztest_noshell_user'


# --- Share Permission Combination Tests ---
def test_share_permission_combinations(initial_state) -> None:
    """Test various combinations of share permissions."""
    # Create users for testing
    cmd = "create user sztest_perm_user1 --password 'PermPass1!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_perm_user1' created successfully.", json=True)

    cmd = "create user sztest_perm_user2 --password 'PermPass2!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_perm_user2' created successfully.", json=True)

    cmd = "create group sztest_perm_group --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_perm_group' created successfully.", json=True)

    # Share with user and group permissions
    cmd = "create share mixed_perms --dataset shares/mixed_perms --valid-users sztest_perm_user1,@sztest_perm_group --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'mixed_perms' created successfully.", json=True)

    # Read-only share
    cmd = "create share readonly_share --dataset shares/readonly_share --readonly --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'readonly_share' created successfully.", json=True)

    # Non-browseable share
    cmd = "create share hidden_share --dataset shares/hidden_share --no-browse --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'hidden_share' created successfully.", json=True)

    # Share with custom ownership
    cmd = "create share custom_own --dataset shares/custom_own --owner sztest_perm_user1 --group sztest_perm_group --perms 750 --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'custom_own' created successfully.", json=True)

    # Verify state
    state = run_smb_zfs_command("get-state")
    assert 'mixed_perms' in state['shares']
    assert 'readonly_share' in state['shares']
    assert 'hidden_share' in state['shares']
    assert 'custom_own' in state['shares']

    # Verify share configurations
    assert 'sztest_perm_user1' in state['shares']['smb']['mixed_perms']['smb_config']['valid_users']
    assert '@sztest_perm_group' in state['shares']['smb']['mixed_perms']['smb_config']['valid_users']
    assert state['shares']['smb']['readonly_share']['smb_config']['read_only'] == True
    assert state['shares']['smb']['hidden_share']['smb_config']['browseable'] == False

    # Verify ZFS datasets
    assert get_zfs_property(
        'primary_testpool/shares/mixed_perms', 'type') == 'filesystem'
    assert get_zfs_property(
        'primary_testpool/shares/readonly_share', 'type') == 'filesystem'
    assert get_zfs_property(
        'primary_testpool/shares/hidden_share', 'type') == 'filesystem'
    assert get_zfs_property(
        'primary_testpool/shares/custom_own', 'type') == 'filesystem'

    # Verify filesystem permissions for custom_own
    mountpoint = get_zfs_property(
        'primary_testpool/shares/custom_own', 'mountpoint')
    assert 750 == get_file_permissions(mountpoint)
    owner, group = get_owner_and_group(mountpoint)
    assert owner == 'sztest_perm_user1'
    assert group == 'sztest_perm_group'

    # Verify smb.conf
    smb_conf = read_smb_conf()
    assert '[mixed_perms]' in smb_conf
    assert '[readonly_share]' in smb_conf
    assert '[hidden_share]' in smb_conf
    assert '[custom_own]' in smb_conf
    assert 'valid users = sztest_perm_user1,@sztest_perm_group' in smb_conf
    assert 'read only = yes' in smb_conf
    assert 'browseable = no' in smb_conf


# --- Quota Format and Edge Case Tests ---
def test_quota_format_variations(initial_state) -> None:
    """Test different quota format specifications."""
    cmd = "create user sztest_quota_user --password 'QuotaPass!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_quota_user' created successfully.", json=True)

    # Verify state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_quota_user' in state['users']

    # Test different quota formats
    quota_formats = ['1G', '512M', '2T', '500G']

    for quota in quota_formats:
        cmd = f"modify home sztest_quota_user --quota {quota} --json"
        result = run_smb_zfs_command(cmd)
        check_smb_zfs_result(
            result, f"Quota for user 'sztest_quota_user' has been set to {quota}.", json=True)

        # Verify ZFS quota
        assert get_zfs_property(
            'primary_testpool/homes/sztest_quota_user', 'quota') == quota

    # Test removing quota
    cmd = "modify home sztest_quota_user --quota none --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Quota for user 'sztest_quota_user' has been set to none.", json=True)

    # Verify quota removal
    assert get_zfs_property(
        'primary_testpool/homes/sztest_quota_user', 'quota') == 'none'


def test_share_quota_variations(initial_state) -> None:
    """Test share quota variations."""
    cmd = "create share quota_share --dataset shares/quota_share --quota 10G --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'quota_share' created successfully.", json=True)

    # Verify state
    state = run_smb_zfs_command("get-state")
    assert 'quota_share' in state['shares']

    # Verify initial quota
    assert get_zfs_property(
        'primary_testpool/shares/quota_share', 'quota') == '10G'

    # Modify quota
    cmd = "modify share quota_share --quota 20G --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'quota_share' modified successfully.", json=True)

    # Verify updated state
    state = run_smb_zfs_command("get-state")
    assert 'quota_share' in state['shares']

    # Verify modified quota
    assert get_zfs_property(
        'primary_testpool/shares/quota_share', 'quota') == '20G'

    # Verify smb.conf
    smb_conf = read_smb_conf()
    assert '[quota_share]' in smb_conf
    assert 'path = /primary_testpool/shares/quota_share' in smb_conf


# --- Group Membership Edge Case Tests ---
def test_group_membership_complex_operations(initial_state) -> None:
    """Test complex group membership operations."""
    # Create users
    cmd = "create user sztest_member1 --password 'Member1!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_member1' created successfully.", json=True)

    cmd = "create user sztest_member2 --password 'Member2!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_member2' created successfully.", json=True)

    cmd = "create user sztest_member3 --password 'Member3!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_member3' created successfully.", json=True)

    cmd = "create group sztest_complex_group --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_complex_group' created successfully.", json=True)

    # Add multiple users at once
    cmd = "modify group sztest_complex_group --add-users sztest_member1,sztest_member2,sztest_member3 --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_complex_group' modified successfully.", json=True)

    # Verify state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_member1' in state['users']
    assert 'sztest_member2' in state['users']
    assert 'sztest_member3' in state['users']
    assert 'sztest_complex_group' in state['groups']

    # Verify all are members
    for user in ['sztest_member1', 'sztest_member2', 'sztest_member3']:
        user_details = get_system_user_details(user)
        assert user_details is not None
        assert 'sztest_complex_group' in user_details

    # Remove some users
    cmd = "modify group sztest_complex_group --remove-users sztest_member1,sztest_member3 --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_complex_group' modified successfully.", json=True)

    # Verify updated state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_complex_group' in state['groups']

    # Verify membership changes
    member1_details = get_system_user_details('sztest_member1')
    member2_details = get_system_user_details('sztest_member2')
    member3_details = get_system_user_details('sztest_member3')

    assert 'sztest_complex_group' not in member1_details
    assert 'sztest_complex_group' in member2_details
    assert 'sztest_complex_group' not in member3_details


# --- State File Operation Tests ---
def test_get_state_comprehensive(initial_state) -> None:
    """Test comprehensive state retrieval."""
    # Create various resources
    cmd = "create user sztest_state_user --password 'StatePass!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_state_user' created successfully.", json=True)

    cmd = "create group sztest_state_group --description 'State test group' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_state_group' created successfully.", json=True)

    cmd = "create share state_share --dataset shares/state_share --comment 'State test share' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'state_share' created successfully.", json=True)

    # Get comprehensive state
    state = run_smb_zfs_command("get-state")

    # Verify state structure
    assert isinstance(state, dict)
    assert 'users' in state
    assert 'groups' in state
    assert 'shares' in state

    # Verify specific entries exist
    assert 'sztest_state_user' in state['users']
    assert 'sztest_state_group' in state['groups']
    assert 'state_share' in state['shares']

    # Verify nested structure and content
    assert isinstance(state['users'], dict)
    assert isinstance(state['groups'], dict)
    assert isinstance(state['shares'], dict)

    # Verify share has expected structure
    share_config = state['shares']['smb']['state_share']
    assert 'smb_config' in share_config
    assert share_config['smb_config']['comment'] == 'State test share'

    # Verify system resources exist
    assert get_system_user_details('sztest_state_user') is not None
    assert get_zfs_property(
        'primary_testpool/homes/sztest_state_user', 'type') == 'filesystem'
    assert get_zfs_property(
        'primary_testpool/shares/state_share', 'type') == 'filesystem'

    # Verify smb.conf
    smb_conf = read_smb_conf()
    assert '[state_share]' in smb_conf
    assert 'comment = State test share' in smb_conf


# --- Error Condition and Recovery Tests ---
def test_invalid_pool_operations(initial_state) -> None:
    """Test operations with invalid pools."""
    # Try to create share on non-existent pool
    cmd = "create share invalid_pool_share --dataset shares/invalid_pool_share --pool nonexistent_pool --json"
    result = run_smb_zfs_command(cmd)

    # Verify error message
    expected_error = "Error: Pool 'nonexistent_pool' is not a valid pool. Managed pools are: primary_testpool, secondary_testpool, tertiary_testpool"
    assert result == expected_error

    # Verify state unchanged
    state = run_smb_zfs_command("get-state")
    assert 'invalid_pool_share' not in state['shares']

    # Verify no ZFS dataset created
    assert get_zfs_property(
        'nonexistent_pool/shares/invalid_pool_share', 'type') is None

    # Verify no smb.conf entry
    smb_conf = read_smb_conf()
    assert '[invalid_pool_share]' not in smb_conf


def test_invalid_user_references(initial_state) -> None:
    """Test operations referencing invalid users."""
    # Create group for testing
    cmd = "create group sztest_test_group --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_test_group' created successfully.", json=True)

    # Try to add non-existent user to group
    cmd = "modify group sztest_test_group --add-users sztest_nonexistent_user --json"
    result = run_smb_zfs_command(cmd)
    expected_error = "Error: User 'sztest_nonexistent_user' not found or not managed by this tool."
    assert result == expected_error

    # Verify group state unchanged
    state = run_smb_zfs_command("get-state")
    assert 'sztest_test_group' in state['groups']
    assert get_system_group_exists('sztest_test_group')

    # Try to create share with non-existent user
    cmd = "create share invalid_user_share --dataset shares/invalid_user_share --valid-users nonexistent_user --json"
    result = run_smb_zfs_command(cmd)
    expected_error = "Error: User 'nonexistent_user' not found or not managed by this tool."
    assert expected_error in result

    # Verify share not created
    state = run_smb_zfs_command("get-state")
    assert 'invalid_user_share' not in state['shares']
    assert get_zfs_property(
        'primary_testpool/shares/invalid_user_share', 'type') is None

    # Verify no smb.conf entry
    smb_conf = read_smb_conf()
    assert '[invalid_user_share]' not in smb_conf


def test_dataset_path_variations(initial_state) -> None:
    """Test different dataset path formats."""
    # Test various dataset path formats
    dataset_paths = [
        'shares/simple',
        'shares/nested/path',
        'shares/deeply/nested/path/structure'
    ]

    for i, path in enumerate(dataset_paths):
        share_name = f"path_test_{i}"
        cmd = f"create share {share_name} --dataset {path} --json"
        result = run_smb_zfs_command(cmd)
        check_smb_zfs_result(
            result, f"Share '{share_name}' created successfully.", json=True)

        # Verify state
        state = run_smb_zfs_command("get-state")
        assert share_name in state['shares']

        # Verify ZFS dataset created with correct path
        expected_dataset = f"primary_testpool/{path}"
        assert get_zfs_property(expected_dataset, 'type') == 'filesystem'
        assert get_zfs_property(
            expected_dataset, 'mountpoint') == f"/{expected_dataset}"

        # Verify smb.conf entry
        smb_conf = read_smb_conf()
        assert f'[{share_name}]' in smb_conf
        assert f'path = /{expected_dataset}' in smb_conf


# --- Multiple Operations Sequence Tests ---
def test_multiple_operations_sequence(initial_state) -> None:
    """Test sequence of multiple operations."""
    # Define operations with expected success messages
    operations = [
        ("create user sztest_workflow_user --password 'WorkflowPass!' --json",
         "User 'sztest_workflow_user' created successfully."),
        ("create group sztest_workflow_group --description 'Workflow group' --json",
         "Group 'sztest_workflow_group' created successfully."),
        ("modify group sztest_workflow_group --add-users sztest_workflow_user --json",
         "Group 'sztest_workflow_group' modified successfully."),
        ("create share workflow_share --dataset shares/workflow_share --valid-users @sztest_workflow_group --json",
         "Share 'workflow_share' created successfully."),
        ("modify share workflow_share --comment 'Modified workflow share' --quota 15G --json",
         "Share 'workflow_share' modified successfully."),
        ("modify home sztest_workflow_user --quota 5G --json",
         "Quota for user 'sztest_workflow_user' has been set to 5G.")
    ]

    # Execute operations in sequence and verify each step
    for cmd, expected_msg in operations:
        result = run_smb_zfs_command(cmd)
        check_smb_zfs_result(result, expected_msg, json=True)

    # Verify final state
    final_state = run_smb_zfs_command("get-state")

    # Check all resources exist
    assert 'sztest_workflow_user' in final_state['users']
    assert 'sztest_workflow_group' in final_state['groups']
    assert 'workflow_share' in final_state['shares']

    # Check final configurations
    assert final_state['shares']['smb']['workflow_share']['smb_config']['comment'] == 'Modified workflow share'
    assert '@sztest_workflow_group' in final_state['shares']['smb']['workflow_share']['smb_config']['valid_users']

    # Verify system changes
    assert get_system_user_details('sztest_workflow_user') is not None
    assert get_system_group_exists('sztest_workflow_group')
    user_details = get_system_user_details('sztest_workflow_user')
    assert 'sztest_workflow_group' in user_details

    # Verify ZFS properties
    assert get_zfs_property(
        'primary_testpool/shares/workflow_share', 'quota') == '15G'
    assert get_zfs_property(
        'primary_testpool/homes/sztest_workflow_user', 'quota') == '5G'
    assert get_zfs_property(
        'primary_testpool/shares/workflow_share', 'type') == 'filesystem'
    assert get_zfs_property(
        'primary_testpool/homes/sztest_workflow_user', 'type') == 'filesystem'

    # Verify smb.conf
    smb_conf = read_smb_conf()
    assert '[workflow_share]' in smb_conf
    assert 'comment = Modified workflow share' in smb_conf
    assert 'valid users = @sztest_workflow_group' in smb_conf


# --- Boolean Flag Modification Tests ---
def test_modify_share_boolean_flags(initial_state) -> None:
    """Test share modification with boolean flag variations."""
    # Create initial share
    cmd = "create share bool_share --dataset shares/bool_share --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'bool_share' created successfully.", json=True)

    # Verify initial state
    state = run_smb_zfs_command("get-state")
    assert 'bool_share' in state['shares']
    initial_readonly = state['shares']['smb']['bool_share']['smb_config'].get(
        'read_only', False)
    initial_browseable = state['shares']['smb']['bool_share']['smb_config'].get(
        'browseable', True)

    # Test enabling readonly
    cmd = "modify share bool_share --readonly --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'bool_share' modified successfully.", json=True)

    state = run_smb_zfs_command("get-state")
    assert state['shares']['smb']['bool_share']['smb_config']['read_only'] == True

    # Verify smb.conf
    smb_conf = read_smb_conf()
    assert 'read only = yes' in smb_conf

    # Test enabling no-browse
    cmd = "modify share bool_share --no-browse --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'bool_share' modified successfully.", json=True)

    state = run_smb_zfs_command("get-state")
    assert state['shares']['smb']['bool_share']['smb_config']['browseable'] == False
    # Should persist
    assert state['shares']['smb']['bool_share']['smb_config']['read_only'] == True

    # Verify smb.conf has both settings
    smb_conf = read_smb_conf()
    assert 'browseable = no' in smb_conf
    assert 'read only = yes' in smb_conf

    # Verify ZFS dataset still exists
    assert get_zfs_property(
        'primary_testpool/shares/bool_share', 'type') == 'filesystem'


# --- Cleanup and Deletion Edge Case Tests ---
def test_delete_user_with_group_membership(initial_state) -> None:
    """Test deleting user who is member of groups."""
    # Create user
    cmd = "create user sztest_member_user --password 'MemberPass!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_member_user' created successfully.", json=True)

    # Create group with user
    cmd = "create group sztest_member_group --users sztest_member_user --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_member_group' created successfully.", json=True)

    # Verify user is in group
    user_details = get_system_user_details('sztest_member_user')
    assert user_details is not None
    assert 'sztest_member_group' in user_details

    # Verify initial state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_member_user' in state['users']
    assert 'sztest_member_group' in state['groups']

    # Delete user
    cmd = "delete user sztest_member_user --yes --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_member_user' deleted successfully.", json=True)

    # Verify final state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_member_user' not in state['users']
    assert 'sztest_member_group' in state['groups']  # Group should still exist

    # Verify system changes
    assert get_system_user_details('sztest_member_user') is None
    assert get_system_group_exists('sztest_member_group')

    # Verify Data is not deleted
    assert get_zfs_property(
        'primary_testpool/homes/sztest_member_user', 'type') == 'filesystem'


def test_delete_group_with_members(initial_state) -> None:
    """Test deleting group that has members."""
    # Create user
    cmd = "create user sztest_group_member --password 'GroupMemberPass!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_group_member' created successfully.", json=True)

    # Create group with user
    cmd = "create group sztest_member_group --users sztest_group_member --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_member_group' created successfully.", json=True)

    # Verify initial state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_group_member' in state['users']
    assert 'sztest_member_group' in state['groups']

    # Verify user is in group
    user_details = get_system_user_details('sztest_group_member')
    assert 'sztest_member_group' in user_details

    # Delete group
    cmd = "delete group sztest_member_group --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_member_group' deleted successfully.", json=True)

    # Verify final state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_member_group' not in state['groups']
    assert 'sztest_group_member' in state['users']  # User should remain

    # Verify system changes
    assert not get_system_group_exists('sztest_member_group')
    assert get_system_user_details('sztest_group_member') is not None

    # Verify user is no longer in the deleted group
    user_details = get_system_user_details('sztest_group_member')
    assert 'sztest_member_group' not in user_details

    # Verify user's home directory still exists
    assert get_zfs_property(
        'primary_testpool/homes/sztest_group_member', 'type') == 'filesystem'


def test_delete_share_with_dependencies(initial_state) -> None:
    """Test deleting share that's referenced by users."""
    # Create user
    cmd = "create user sztest_share_user --password 'ShareUserPass!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_share_user' created successfully.", json=True)

    # Create share with user dependency
    cmd = "create share dependent_share --dataset shares/dependent_share --valid-users sztest_share_user --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'dependent_share' created successfully.", json=True)

    # Verify initial state
    state = run_smb_zfs_command("get-state")
    assert 'dependent_share' in state['shares']
    assert 'sztest_share_user' in state['users']
    assert 'sztest_share_user' in state['shares']['smb']['dependent_share']['smb_config']['valid_users']

    # Verify ZFS and smb.conf
    assert get_zfs_property(
        'primary_testpool/shares/dependent_share', 'type') == 'filesystem'
    smb_conf = read_smb_conf()
    assert '[dependent_share]' in smb_conf
    assert 'valid users = sztest_share_user' in smb_conf

    # Delete share
    cmd = "delete share dependent_share --yes --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'dependent_share' deleted successfully.", json=True)

    # Verify final state
    state = run_smb_zfs_command("get-state")
    assert 'dependent_share' not in state['shares']
    assert 'sztest_share_user' in state['users']  # User should remain

    # Verify system changes
    assert get_system_user_details('sztest_share_user') is not None
    assert get_zfs_property(
        'primary_testpool/homes/sztest_share_user', 'type') == 'filesystem'

    # Verify share cleanup
    assert get_zfs_property('primary_testpool/shares/dependent_share',
                            'type') == 'filesystem'  # Dataset should remain by default

    # Verify smb.conf cleanup
    smb_conf = read_smb_conf()
    assert '[dependent_share]' not in smb_conf


# --- Complex Remove Scenario Tests ---
def test_remove_users_with_complex_setup() -> None:
    """Test remove command with complex setup - users only."""
    # Initial cleanup
    cmd = "remove --delete-users --delete-data --yes"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Removal completed successfully.", json=False)

    # Create complex setup
    cmd = "setup --primary-pool primary_testpool --secondary-pools secondary_testpool tertiary_testpool --server-name COMPLEXTEST --workgroup COMPLEXGROUP --macos --default-home-quota 25G"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Setup completed successfully.", json=False)

    # Add complex data
    cmd = "create user sztest_complex1 --password 'Complex1!' --shell --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_complex1' created successfully.", json=True)

    cmd = "create user sztest_complex2 --password 'Complex2!' --no-home --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_complex2' created successfully.", json=True)

    cmd = "create group sztest_complex_group --users sztest_complex1 --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_complex_group' created successfully.", json=True)

    cmd = "create share complex_share1 --dataset shares/complex_share1 --pool primary_testpool --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'complex_share1' created successfully.", json=True)

    cmd = "create share complex_share2 --dataset shares/complex_share2 --pool secondary_testpool --valid-users @sztest_complex_group --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'complex_share2' created successfully.", json=True)

    # Verify initial state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_complex1' in state['users']
    assert 'sztest_complex2' in state['users']
    assert 'sztest_complex_group' in state['groups']
    assert 'complex_share1' in state['shares']
    assert 'complex_share2' in state['shares']

    # Test partial remove (users only)
    cmd = "remove --delete-users --yes --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Removal completed successfully.", json=True)

    # Verify system users removed
    assert get_system_user_details('sztest_complex1') is None
    assert get_system_user_details('sztest_complex2') is None

    # Datasets should still exist (data not deleted)
    assert get_zfs_property(
        'primary_testpool/homes/sztest_complex1', 'type') == 'filesystem'
    assert get_zfs_property(
        'primary_testpool/shares/complex_share1', 'type') == 'filesystem'
    assert get_zfs_property(
        'secondary_testpool/shares/complex_share2', 'type') == 'filesystem'

    # Verify smb.conf still has shares
    smb_conf = read_smb_conf()
    assert '[complex_share1]' in smb_conf
    assert '[complex_share2]' in smb_conf


def test_remove_data_with_complex_setup() -> None:
    """Test remove command with complex setup - data only."""
    # Initial cleanup
    cmd = "remove --delete-users --delete-data --yes"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Removal completed successfully.", json=False)

    # Create complex setup
    cmd = "setup --primary-pool primary_testpool --secondary-pools secondary_testpool tertiary_testpool --server-name COMPLEXTEST --workgroup COMPLEXGROUP --macos --default-home-quota 25G"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Setup completed successfully.", json=False)

    # Add complex data
    cmd = "create user sztest_complex1 --password 'Complex1!' --shell --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_complex1' created successfully.", json=True)

    cmd = "create user sztest_complex2 --password 'Complex2!' --no-home --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_complex2' created successfully.", json=True)

    cmd = "create group sztest_complex_group --users sztest_complex1 --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_complex_group' created successfully.", json=True)

    cmd = "create share complex_share1 --dataset shares/complex_share1 --pool primary_testpool --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'complex_share1' created successfully.", json=True)

    cmd = "create share complex_share2 --dataset shares/complex_share2 --pool secondary_testpool --valid-users @sztest_complex_group --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'complex_share2' created successfully.", json=True)

    # Verify initial state and data
    state = run_smb_zfs_command("get-state")
    assert 'sztest_complex1' in state['users']
    assert 'sztest_complex2' in state['users']
    assert get_zfs_property(
        'primary_testpool/homes/sztest_complex1', 'type') == 'filesystem'
    assert get_zfs_property(
        'primary_testpool/shares/complex_share1', 'type') == 'filesystem'

    # Test data-only removal
    cmd = "remove --delete-data --yes --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Removal completed successfully.", json=True)

    # Verify users remain on system
    assert get_system_user_details('sztest_complex1') is not None
    assert get_system_user_details('sztest_complex2') is not None

    # Verify groups remain
    assert get_system_group_exists('sztest_complex_group')

    # All data should be gone
    assert get_zfs_property('primary_testpool/homes', 'type') is None
    assert get_zfs_property('primary_testpool/shares/complex_share1', 'type') is None
    assert get_zfs_property('secondary_testpool/shares/complex_share2', 'type') is None

    smb_conf = read_smb_conf()
    assert '[complex_share1]' not in smb_conf
    assert '[complex_share2]' not in smb_conf


# --- Parameter Validation Tests ---
def test_invalid_parameter_combinations(initial_state) -> None:
    """Test commands with invalid parameter combinations."""
    # Create user and group for testing
    cmd = "create user sztest_complex1 --password 'Complex1!' --shell --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_complex1' created successfully.", json=True)

    cmd = "create group sztest_comp_group1 --users sztest_complex1 --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Group 'sztest_comp_group1' created successfully.", json=True)

    # Verify initial state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_complex1' in state['users']
    assert 'sztest_comp_group1' in state['groups']

    # Try to modify group without any modification flags
    cmd = "modify group sztest_comp_group1 --json"
    result = run_smb_zfs_command(cmd)
    expected_error = "Error: Found no users to add or remove!"
    assert result == expected_error

    # Verify state unchanged after error
    state = run_smb_zfs_command("get-state")
    assert 'sztest_comp_group1' in state['groups']
    assert get_system_group_exists('sztest_comp_group1')

    # Verify user still in group
    user_details = get_system_user_details('sztest_complex1')
    assert 'sztest_comp_group1' in user_details


# --- Dataset Structure Tests ---
def test_dataset_structure_consistency(initial_state) -> None:
    """Test that dataset structure is consistent."""
    # Create resources
    cmd = "create user sztest_struct_user --password 'StructPass!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_struct_user' created successfully.", json=True)

    cmd = "create share struct_share --dataset shares/struct_share --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'struct_share' created successfully.", json=True)

    # Verify state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_struct_user' in state['users']
    assert 'struct_share' in state['shares']

    # Verify consistent naming structure
    assert get_zfs_property(
        'primary_testpool/homes/sztest_struct_user', 'type') == 'filesystem'
    assert get_zfs_property(
        'primary_testpool/shares/struct_share', 'type') == 'filesystem'

    # Verify mountpoints are correct
    user_mountpoint = get_zfs_property(
        'primary_testpool/homes/sztest_struct_user', 'mountpoint')
    share_mountpoint = get_zfs_property(
        'primary_testpool/shares/struct_share', 'mountpoint')

    assert user_mountpoint == '/primary_testpool/homes/sztest_struct_user'
    assert share_mountpoint == '/primary_testpool/shares/struct_share'

    # Verify system user exists
    assert get_system_user_details('sztest_struct_user') is not None

    # Verify smb.conf structure
    smb_conf = read_smb_conf()
    assert '[struct_share]' in smb_conf
    assert f'path = {share_mountpoint}' in smb_conf


# --- Configuration File Consistency Tests ---
def test_smb_conf_consistency(initial_state) -> None:
    """Test that smb.conf stays consistent with state."""
    # Create share with specific configuration
    cmd = "create share conf_share --dataset shares/conf_share --comment 'Config test share' --readonly --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'conf_share' created successfully.", json=True)

    # Get initial state and smb.conf
    state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    # Verify state matches smb.conf
    assert 'conf_share' in state['shares']
    share_config = state['shares']['smb']['conf_share']['smb_config']

    assert '[conf_share]' in smb_conf
    assert f"comment = {share_config['comment']}" in smb_conf
    read_only_value = 'yes' if share_config['read_only'] else 'no'
    assert f"read only = {read_only_value}" in smb_conf

    # Verify ZFS dataset
    assert get_zfs_property(
        'primary_testpool/shares/conf_share', 'type') == 'filesystem'

    # Modify share and verify consistency
    cmd = "modify share conf_share --comment 'Modified config test' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'conf_share' modified successfully.", json=True)

    # Get updated state and smb.conf
    updated_state = run_smb_zfs_command("get-state")
    updated_smb_conf = read_smb_conf()

    # Verify consistency after modification
    updated_share_config = updated_state['shares']['smb']['conf_share']['smb_config']
    assert updated_share_config['comment'] == 'Modified config test'
    assert "comment = Modified config test" in updated_smb_conf

    # Verify read-only setting persisted
    assert updated_share_config['read_only'] == True
    assert "read only = yes" in updated_smb_conf


# --- System Integration Tests ---
def test_system_user_integration(initial_state) -> None:
    """Test integration with system user management."""
    cmd = "create user sztest_sys_user --password 'SysPass!' --shell --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "User 'sztest_sys_user' created successfully.", json=True)

    # Verify state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_sys_user' in state['users']

    # Verify system user exists and has correct properties
    user_details = get_system_user_details('sztest_sys_user')
    assert user_details is not None

    user_shell = get_system_user_shell('sztest_sys_user')
    assert user_shell is not None
    assert '/bin/bash' in user_shell  # Should have shell when --shell is used

    # Verify user is in smb_users group (created during setup)
    assert 'smb_users' in user_details

    # Verify ZFS home directory
    assert get_zfs_property(
        'primary_testpool/homes/sztest_sys_user', 'type') == 'filesystem'
    assert get_zfs_property('primary_testpool/homes/sztest_sys_user',
                            'mountpoint') == '/primary_testpool/homes/sztest_sys_user'


def test_comprehensive_workflow(initial_state) -> None:
    """Test a comprehensive workflow simulating real usage."""
    # Simulate setting up a complete SMB environment

    # 1. Create departments (groups)
    departments = ['sztest_engineering', 'sztest_marketing', 'sztest_finance']
    for dept in departments:
        cmd = f"create group {dept} --description '{dept.replace('sztest_', '').capitalize()} department' --json"
        result = run_smb_zfs_command(cmd)
        check_smb_zfs_result(
            result, f"Group '{dept}' created successfully.", json=True)

    # 2. Create users for each department
    users = [
        ('sztest_alice', 'sztest_engineering'),
        ('sztest_bob', 'sztest_engineering'),
        ('sztest_carol', 'sztest_marketing'),
        ('sztest_dave', 'sztest_finance')
    ]

    for username, dept in users:
        cmd = f"create user {username} --password '{username.replace('sztest_', '').capitalize()}Pass!' --shell --json"
        result = run_smb_zfs_command(cmd)
        check_smb_zfs_result(
            result, f"User '{username}' created successfully.", json=True)

        cmd = f"modify group {dept} --add-users {username} --json"
        result = run_smb_zfs_command(cmd)
        check_smb_zfs_result(
            result, f"Group '{dept}' modified successfully.", json=True)

    # 3. Create departmental shares
    for dept in departments:
        share_name = f"{dept}_share"
        dataset_name = dept.replace('sztest_', '')
        cmd = f"create share {share_name} --dataset shares/{dataset_name} --valid-users @{dept} --quota 100G --comment '{dept.replace('sztest_', '').capitalize()} department share' --json"
        result = run_smb_zfs_command(cmd)
        check_smb_zfs_result(
            result, f"Share '{share_name}' created successfully.", json=True)

    # 4. Create a common share
    user_list = ','.join([username for username, _ in users])
    cmd = f"create share common --dataset shares/common --valid-users {user_list} --comment 'Common shared area' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(
        result, "Share 'common' created successfully.", json=True)

    # 5. Set individual quotas
    for username, _ in users:
        cmd = f"modify home {username} --quota 10G --json"
        result = run_smb_zfs_command(cmd)
        check_smb_zfs_result(
            result, f"Quota for user '{username}' has been set to 10G.", json=True)

    # 6. Verify final state
    final_state = run_smb_zfs_command("get-state")

    # Verify all users exist in state and system
    for username, dept in users:
        assert username in final_state['users']
        assert get_system_user_details(username) is not None

        # Verify user is in correct department
        user_details = get_system_user_details(username)
        assert dept in user_details

        # Verify user quotas
        assert get_zfs_property(
            f'primary_testpool/homes/{username}', 'quota') == '10G'
        assert get_zfs_property(
            f'primary_testpool/homes/{username}', 'type') == 'filesystem'

    # Verify all groups exist
    for dept in departments:
        assert dept in final_state['groups']
        assert get_system_group_exists(dept)

    # Verify all shares exist with correct configurations
    for dept in departments:
        share_name = f'{dept}_share'
        dataset_name = dept.replace('sztest_', '')

        assert share_name in final_state['shares']
        assert get_zfs_property(
            f'primary_testpool/shares/{dataset_name}', 'quota') == '100G'
        assert get_zfs_property(
            f'primary_testpool/shares/{dataset_name}', 'type') == 'filesystem'

        # Verify share configuration
        share_config = final_state['shares']['smb'][share_name]['smb_config']
        assert f'@{dept}' in share_config['valid_users']

    # Verify common share
    assert 'common' in final_state['shares']
    assert get_zfs_property(
        'primary_testpool/shares/common', 'type') == 'filesystem'

    common_share_config = final_state['shares']['smb']['common']['smb_config']
    for username, _ in users:
        assert username in common_share_config['valid_users']

    # Verify smb.conf has all shares
    smb_conf = read_smb_conf()
    for dept in departments:
        share_name = f'{dept}_share'
        assert f'[{share_name}]' in smb_conf
    assert '[common]' in smb_conf

    # Verify comprehensive system integration
    assert len(final_state['users']) >= len(users)
    assert len(final_state['groups']) >= len(departments)
    assert len(final_state['shares']) >= len(
        departments) + 1  # departments + common
