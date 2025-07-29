from conftest import (
    run_smb_zfs_command,
    get_system_user_details,
    get_zfs_property,
    read_smb_conf,
    get_file_permissions,
    get_owner_and_group,
    check_smb_zfs_result
)
from smb_zfs.config_generator import MACOS_SETTINGS


# --- JSON Output Consistency Tests ---
def test_json_output_format(comprehensive_setup) -> None:
    """Test that all commands with --json flag return valid JSON."""
    # Test various commands return valid JSON
    commands = [
        ("create user sztest_json_test --password 'JsonTest!' --json", "User 'sztest_json_test' created successfully."),
        ("create group sztest_json_group --json", "Group 'sztest_json_group' created successfully."),
        ("create share json_share --dataset shares/json_share --json", "Share 'json_share' created successfully."),
        ("modify group sztest_comp_group1 --add-users sztest_comp_user1 --json", "Group 'sztest_comp_group1' modified successfully."),
        ("modify share comp_share1 --comment 'Modified via JSON' --json", "Share 'comp_share1' modified successfully."),
        ("modify home sztest_comp_user1 --quota 10G --json", "Quota for user 'sztest_comp_user1' has been set to 10G."),
        ("delete group sztest_json_group --json", "Group 'sztest_json_group' deleted successfully."),
        ("delete share json_share --yes --json", "Share 'json_share' deleted successfully."),
        ("delete user sztest_json_test --yes --json", "User 'sztest_json_test' deleted successfully.")
    ]

    for command, expected_message in commands:
        result = run_smb_zfs_command(command)
        check_smb_zfs_result(result, expected_message, json=True)


# --- Error Handling Tests ---
def test_duplicate_user_creation(comprehensive_setup) -> None:
    """Test creating duplicate users returns appropriate error."""
    cmd = "create user sztest_comp_user1 --password 'DuplicatePass!' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Error: User 'sztest_comp_user1' already exists.", is_error=True)


def test_duplicate_group_creation(comprehensive_setup) -> None:
    """Test creating duplicate groups returns appropriate error."""
    cmd = "create group sztest_comp_group1 --description 'Duplicate group' --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Error: Group 'sztest_comp_group1' already exists.", is_error=True)


def test_duplicate_share_creation(comprehensive_setup) -> None:
    """Test creating duplicate shares returns appropriate error."""
    cmd = "create share comp_share1 --dataset shares/comp_share1_dup --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Error: Share 'comp_share1' already exists.", is_error=True)


def test_nonexistent_user_operations(comprehensive_setup) -> None:
    """Test operations on nonexistent users."""
    commands = [
        ("delete user sztest_nonexistent_user --yes --json", "Error: User 'sztest_nonexistent_user' not found or not managed by this tool."),
        ("modify home sztest_nonexistent_user --quota 5G --json", "Error: User 'sztest_nonexistent_user' not found or not managed by this tool.")
    ]
    
    for cmd, expected_error in commands:
        result = run_smb_zfs_command(cmd)
        check_smb_zfs_result(result, expected_error, is_error=True)


def test_nonexistent_group_operations(comprehensive_setup) -> None:
    """Test operations on nonexistent groups."""
    commands = [
        ("modify group sztest_nonexistent_group --add-users sztest_comp_user1 --json", "Error: Group 'sztest_nonexistent_group' not found or not managed by this tool."),
        ("delete group sztest_nonexistent_group --json", "Error: Group 'sztest_nonexistent_group' not found or not managed by this tool.")
    ]
    
    for cmd, expected_error in commands:
        result = run_smb_zfs_command(cmd)
        check_smb_zfs_result(result, expected_error, is_error=True)


def test_nonexistent_share_operations(comprehensive_setup) -> None:
    """Test operations on nonexistent shares."""
    commands = [
        ("modify share nonexistent_share --comment 'New comment' --json", "Error: Share 'nonexistent_share' not found or not managed by this tool."),
        ("delete share nonexistent_share --yes --json", "Error: Share 'nonexistent_share' not found or not managed by this tool.")
    ]
    
    for cmd, expected_error in commands:
        result = run_smb_zfs_command(cmd)
        check_smb_zfs_result(result, expected_error, is_error=True)


# --- Complex Scenario Tests ---
def test_user_with_multiple_groups(comprehensive_setup) -> None:
    """Test user membership in multiple groups."""
    # Add user to multiple groups
    cmd1 = "modify group sztest_comp_group1 --add-users sztest_comp_user3 --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(result1, "Group 'sztest_comp_group1' modified successfully.", json=True)
    
    cmd2 = "modify group sztest_comp_group2 --add-users sztest_comp_user3 --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Group 'sztest_comp_group2' modified successfully.", json=True)

    # Check system groups
    user_details = get_system_user_details('sztest_comp_user3')
    assert 'sztest_comp_group1' in user_details
    assert 'sztest_comp_group2' in user_details
    
    # Check state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_comp_user3' in state['groups']['sztest_comp_group1']['members']
    assert 'sztest_comp_user3' in state['groups']['sztest_comp_group2']['members']


def test_share_with_complex_permissions(comprehensive_setup) -> None:
    """Test creating and modifying shares with complex permission sets."""
    # Create share with mixed user and group permissions
    cmd = "create share complex_share --dataset shares/complex_share --valid-users sztest_comp_user1,@sztest_comp_group1,sztest_comp_user3 --owner sztest_comp_user1 --group sztest_comp_group1 --perms 770 --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Share 'complex_share' created successfully.", json=True)

    # Check state
    state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert 'complex_share' in state['shares']
    share_config = state['shares']['complex_share']
    assert 'sztest_comp_user1' in share_config['smb_config']['valid_users']
    assert '@sztest_comp_group1' in share_config['smb_config']['valid_users']
    assert 'sztest_comp_user3' in share_config['smb_config']['valid_users']

    # Check ZFS
    assert get_zfs_property('primary_testpool/shares/complex_share', 'type') == 'filesystem'
    
    # Check filesystem permissions
    mountpoint = get_zfs_property('primary_testpool/shares/complex_share', 'mountpoint')
    assert 770 == get_file_permissions(mountpoint)
    owner, group = get_owner_and_group(mountpoint)
    assert owner == 'sztest_comp_user1'
    assert group == 'sztest_comp_group1'
    
    # Check smb.conf
    assert '[complex_share]' in smb_conf
    assert 'valid users = sztest_comp_user1,@sztest_comp_group1,sztest_comp_user3' in smb_conf


def test_quota_operations(comprehensive_setup) -> None:
    """Test various quota operations."""
    # Set quota
    cmd1 = "modify home sztest_comp_user1 --quota 15G --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(result1, "Quota for user 'sztest_comp_user1' has been set to 15G.", json=True)
    
    # Check ZFS quota
    assert get_zfs_property('primary_testpool/homes/sztest_comp_user1', 'quota') == '15G'
    
    # Check state
    state = run_smb_zfs_command("get-state")
    assert state['users']['sztest_comp_user1']['dataset']['quota'] == '15G'

    # Change quota
    cmd2 = "modify home sztest_comp_user1 --quota 25G --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Quota for user 'sztest_comp_user1' has been set to 25G.", json=True)
    
    # Check ZFS quota
    assert get_zfs_property('primary_testpool/homes/sztest_comp_user1', 'quota') == '25G'
    
    # Check state
    state = run_smb_zfs_command("get-state")
    assert state['users']['sztest_comp_user1']['dataset']['quota'] == '25G'

    # Remove quota
    cmd3 = "modify home sztest_comp_user1 --quota none --json"
    result3 = run_smb_zfs_command(cmd3)
    check_smb_zfs_result(result3, "Quota for user 'sztest_comp_user1' has been set to none.", json=True)
    
    # Check ZFS quota
    assert get_zfs_property('primary_testpool/homes/sztest_comp_user1', 'quota') == 'none'
    
    # Check state
    state = run_smb_zfs_command("get-state")
    assert state['users']['sztest_comp_user1']['dataset']['quota'] == 'none'


def test_share_quota_operations(comprehensive_setup) -> None:
    """Test share quota operations."""
    # Modify existing share quota
    cmd1 = "modify share comp_share2 --quota 100G --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(result1, "Share 'comp_share2' modified successfully.", json=True)
    
    # Check ZFS quota
    assert get_zfs_property('secondary_testpool/shares/comp_share2', 'quota') == '100G'
    
    # Check state
    state = run_smb_zfs_command("get-state")
    assert state['shares']['comp_share2']['dataset']['quota'] == '100G'

    # Remove share quota
    cmd2 = "modify share comp_share2 --quota none --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Share 'comp_share2' modified successfully.", json=True)
    
    # Check ZFS quota
    assert get_zfs_property('secondary_testpool/shares/comp_share2', 'quota') == 'none'
    
    # Check state
    state = run_smb_zfs_command("get-state")
    assert state['shares']['comp_share2']['dataset']['quota'] == 'none'


# --- Comprehensive Modify Tests ---
def test_modify_share_all_options(comprehensive_setup) -> None:
    """Test modifying all possible share options."""
    # Create a basic share
    cmd = "create share modify_all --dataset shares/modify_all --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Share 'modify_all' created successfully.", json=True)

    # Modify all possible options
    cmd = "modify share modify_all --pool secondary_testpool --name modify_all_renamed --comment 'Fully modified share' --valid-users sztest_comp_user1,sztest_comp_user2 --owner sztest_comp_user1 --group sztest_comp_group1 --perms 755 --quota 30G --readonly --no-browse --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Share 'modify_all' modified successfully.", json=True)

    state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    # Check State
    share_config = state['shares']['modify_all_renamed']
    assert share_config['smb_config']['comment'] == 'Fully modified share'
    assert share_config['smb_config']['read_only'] == True
    assert share_config['smb_config']['browseable'] == False
    assert 'sztest_comp_user1' in share_config['smb_config']['valid_users']
    assert 'sztest_comp_user2' in share_config['smb_config']['valid_users']

    # Check ZFS
    assert get_zfs_property('secondary_testpool/shares/modify_all_renamed', 'type') == 'filesystem'
    assert get_zfs_property('primary_testpool/shares/modify_all_renamed', 'type') is None
    assert get_zfs_property('secondary_testpool/shares/modify_all_renamed', 'quota') == '30G'
    
    # Check Filesystem
    mountpoint = get_zfs_property('secondary_testpool/shares/modify_all_renamed', 'mountpoint')
    assert 755 == get_file_permissions(mountpoint)
    owner, group = get_owner_and_group(mountpoint)
    assert owner == 'sztest_comp_user1'
    assert group == 'sztest_comp_group1'

    # Check smb.conf
    assert '[modify_all_renamed]' in smb_conf
    assert 'valid users = sztest_comp_user1,sztest_comp_user2' in smb_conf
    assert 'read only = yes' in smb_conf
    assert 'browseable = no' in smb_conf


def test_modify_setup_all_options(comprehensive_setup) -> None:
    """Test modifying all setup options."""
    # Test all setup modification options
    cmd = "modify setup --server-name FULLTEST --workgroup FULLGROUP --macos --default-home-quota 40G --json"
    result = run_smb_zfs_command(cmd)
    check_smb_zfs_result(result, "Global setup modified successfully.", json=True)

    # Check state
    state = run_smb_zfs_command("get-state")
    assert state['server_name'] == 'FULLTEST'
    assert state['workgroup'] == 'FULLGROUP'
    assert state['macos_optimized'] == True
    assert state['default_home_quota'] == '40G'
    
    # Check smb.conf
    smb_conf = read_smb_conf()
    assert 'server string = FULLTEST' in smb_conf
    assert 'workgroup = FULLGROUP' in smb_conf
    assert MACOS_SETTINGS in smb_conf


# --- List Command Tests ---
def test_list_command_outputs(comprehensive_setup) -> None:
    """Test that list commands produce expected output format."""
    # Test list users
    users_output = run_smb_zfs_command("list users")
    assert isinstance(users_output, str)
    assert 'sztest_comp_user1' in users_output
    assert 'sztest_comp_user2' in users_output
    assert 'sztest_comp_user3' in users_output

    # Test list groups
    groups_output = run_smb_zfs_command("list groups")
    assert isinstance(groups_output, str)
    assert 'sztest_comp_group1' in groups_output
    assert 'sztest_comp_group2' in groups_output

    # Test list shares
    shares_output = run_smb_zfs_command("list shares")
    assert isinstance(shares_output, str)
    assert 'comp_share1' in shares_output
    assert 'comp_share2' in shares_output

    # Test list pools
    pools_output = run_smb_zfs_command("list pools")
    assert isinstance(pools_output, str)
    assert 'primary_testpool' in pools_output
    assert 'secondary_testpool' in pools_output


# --- Edge Case Tests ---
def test_empty_password_handling() -> None:
    """Test handling of empty or missing passwords."""
    # Test that commands requiring passwords fail appropriately
    cmd = "create user sztest_empty_pass --json"
    result = run_smb_zfs_command(cmd, [''])
    check_smb_zfs_result(result, "Password cannot be empty.", is_error=True)


def test_special_characters_in_names(comprehensive_setup) -> None:
    """Test handling of special characters in names."""
    # Test with underscores and numbers (should work)
    cmd1 = "create user sztest_test_user_123 --password 'TestPass!' --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(result1, "User 'sztest_test_user_123' created successfully.", json=True)
    
    cmd2 = "create group sztest_test_group_456 --description 'Test group with numbers' --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Group 'sztest_test_group_456' created successfully.", json=True)

    # Check state
    state = run_smb_zfs_command("get-state")
    assert 'sztest_test_user_123' in state['users']
    assert 'sztest_test_group_456' in state['groups']
    assert state['groups']['sztest_test_group_456']['description'] == 'Test group with numbers'
    
    # Check system
    user_details = get_system_user_details('sztest_test_user_123')
    assert user_details is not None
    
    # Check ZFS
    assert get_zfs_property('primary_testpool/homes/sztest_test_user_123', 'type') == 'filesystem'


def test_long_descriptions_and_comments(comprehensive_setup) -> None:
    """Test handling of long descriptions and comments."""
    long_description = "This is a very long description that contains many words and should test the handling of lengthy text in group descriptions and share comments."

    # Create group with long description
    cmd1 = f"create group sztest_long_desc_group --description '{long_description}' --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(result1, "Group 'sztest_long_desc_group' created successfully.", json=True)
    
    # Create share with long comment
    cmd2 = f"create share long_comment_share --dataset shares/long_comment_share --comment '{long_description}' --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Share 'long_comment_share' created successfully.", json=True)

    # Check state
    state = run_smb_zfs_command("get-state")
    assert state['groups']['sztest_long_desc_group']['description'] == long_description
    assert state['shares']['long_comment_share']['smb_config']['comment'] == long_description
    
    # Check ZFS
    assert get_zfs_property('primary_testpool/shares/long_comment_share', 'type') == 'filesystem'
    
    # Check smb.conf
    smb_conf = read_smb_conf()
    assert '[long_comment_share]' in smb_conf
    assert f'comment = {long_description}' in smb_conf


# --- State Consistency Tests ---
def test_state_consistency_after_operations(comprehensive_setup) -> None:
    """Test that state remains consistent after various operations."""
    initial_state = run_smb_zfs_command("get-state")

    # Perform various operations
    cmd1 = "create user sztest_state_test --password 'StateTest!' --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(result1, "User 'sztest_state_test' created successfully.", json=True)
    
    cmd2 = "modify group sztest_comp_group1 --add-users sztest_state_test --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Group 'sztest_comp_group1' modified successfully.", json=True)
    
    cmd3 = "create share state_share --dataset shares/state_share --valid-users sztest_state_test --json"
    result3 = run_smb_zfs_command(cmd3)
    check_smb_zfs_result(result3, "Share 'state_share' created successfully.", json=True)

    final_state = run_smb_zfs_command("get-state")

    # Verify state consistency
    assert 'sztest_state_test' in final_state['users']
    assert 'state_share' in final_state['shares']
    assert len(final_state['users']) == len(initial_state['users']) + 1
    assert len(final_state['shares']) == len(initial_state['shares']) + 1
    
    # Check user in group
    assert 'sztest_state_test' in final_state['groups']['sztest_comp_group1']['members']
    
    # Check share configuration
    assert 'sztest_state_test' in final_state['shares']['state_share']['smb_config']['valid_users']
    
    # Check system consistency
    user_details = get_system_user_details('sztest_state_test')
    assert 'sztest_comp_group1' in user_details
    
    # Check ZFS consistency
    assert get_zfs_property('primary_testpool/homes/sztest_state_test', 'type') == 'filesystem'
    assert get_zfs_property('primary_testpool/shares/state_share', 'type') == 'filesystem'
    
    # Check smb.conf consistency
    smb_conf = read_smb_conf()
    assert '[state_share]' in smb_conf
    assert 'valid users = sztest_state_test' in smb_conf


def test_cleanup_operations(comprehensive_setup) -> None:
    """Test that cleanup operations work correctly."""
    # Create temporary resources
    cmd1 = "create user sztest_cleanup_user --password 'CleanupPass!' --json"
    result1 = run_smb_zfs_command(cmd1)
    check_smb_zfs_result(result1, "User 'sztest_cleanup_user' created successfully.", json=True)
    
    cmd2 = "create group sztest_cleanup_group --json"
    result2 = run_smb_zfs_command(cmd2)
    check_smb_zfs_result(result2, "Group 'sztest_cleanup_group' created successfully.", json=True)
    
    cmd3 = "create share cleanup_share --dataset shares/cleanup_share --json"
    result3 = run_smb_zfs_command(cmd3)
    check_smb_zfs_result(result3, "Share 'cleanup_share' created successfully.", json=True)

    # Verify they exist
    state = run_smb_zfs_command("get-state")
    assert 'sztest_cleanup_user' in state['users']
    assert 'sztest_cleanup_group' in state['groups']
    assert 'cleanup_share' in state['shares']
    
    # Check system existence
    user_details = get_system_user_details('sztest_cleanup_user')
    assert user_details is not None
    
    # Check ZFS existence
    assert get_zfs_property('primary_testpool/homes/sztest_cleanup_user', 'type') == 'filesystem'
    assert get_zfs_property('primary_testpool/shares/cleanup_share', 'type') == 'filesystem'

    # Clean them up
    cmd4 = "delete user sztest_cleanup_user --delete-data --yes --json"
    result4 = run_smb_zfs_command(cmd4)
    check_smb_zfs_result(result4, "User 'sztest_cleanup_user' deleted successfully.", json=True)
    
    cmd5 = "delete group sztest_cleanup_group --json"
    result5 = run_smb_zfs_command(cmd5)
    check_smb_zfs_result(result5, "Group 'sztest_cleanup_group' deleted successfully.", json=True)
    
    cmd6 = "delete share cleanup_share --delete-data --yes --json"
    result6 = run_smb_zfs_command(cmd6)
    check_smb_zfs_result(result6, "Share 'cleanup_share' deleted successfully.", json=True)

    # Verify they're gone
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_cleanup_user' not in final_state['users']
    assert 'sztest_cleanup_group' not in final_state['groups']
    assert 'cleanup_share' not in final_state['shares']
    
    # Check system cleanup
    user_details = get_system_user_details('sztest_cleanup_user')
    assert user_details is None
    
    # Check ZFS cleanup
    assert get_zfs_property('primary_testpool/homes/sztest_cleanup_user', 'type') is None
    assert get_zfs_property('primary_testpool/shares/cleanup_share', 'type') is None
    
    # Check smb.conf cleanup
    smb_conf = read_smb_conf()
    assert '[cleanup_share]' not in smb_conf