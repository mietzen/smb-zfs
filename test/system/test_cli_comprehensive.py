import json
from conftest import (
    run_smb_zfs_command,
    get_system_user_details,
    get_zfs_property,
    read_smb_conf,
    get_owner_and_group,
    get_file_permissions
)


# --- JSON Output Consistency Tests ---
def test_json_output_format(comprehensive_setup):
    """Test that all commands with --json flag return valid JSON."""
    # Test various commands return valid JSON
    commands = [
        "create user sztest_json_test --password 'JsonTest!' --json",
        "create group sztest_json_group --json",
        "create share json_share --dataset shares/json_share --json",
        "modify group sztest_comp_group1 --add-users sztest_comp_user1 --json",
        "modify share comp_share1 --comment 'Modified via JSON' --json",
        "modify home sztest_comp_user1 --quota 10G --json",
        "delete group sztest_json_group --json",
        "delete share json_share --yes --json",
        "delete user sztest_json_test --yes --json"
    ]

    for command in commands:
        result = run_smb_zfs_command(command)
        # Should be valid JSON (will raise exception if not)
        assert isinstance(result, dict)
        # Should have a message or relevant data
        assert len(result) > 0


# --- Error Handling Tests ---
def test_duplicate_user_creation(comprehensive_setup):
    """Test creating duplicate users returns appropriate error."""
    result = run_smb_zfs_command(
        "create user sztest_comp_user1 --password 'DuplicatePass!' --json")
    assert result == "Error: User 'sztest_comp_user1' already exists."


def test_duplicate_group_creation(comprehensive_setup):
    """Test creating duplicate groups returns appropriate error."""
    result = run_smb_zfs_command(
        "create group sztest_comp_group1 --description 'Duplicate group' --json")
    assert result == "Error: Group 'sztest_comp_group1' already exists."


def test_duplicate_share_creation(comprehensive_setup):
    """Test creating duplicate shares returns appropriate error."""
    result = run_smb_zfs_command(
        "create share comp_share1 --dataset shares/comp_share1_dup --json")
    assert result == "Error: Share 'comp_share1' already exists."


def test_nonexistent_user_operations(comprehensive_setup):
    """Test operations on nonexistent users."""
    commands = [
        "delete user sztest_nonexistent_user --yes --json",
        "modify home sztest_nonexistent_user --quota 5G --json"
    ]
    for cmd in commands:
        result = run_smb_zfs_command(cmd)
        assert result == "Error: User 'sztest_nonexistent_user' not found or not managed by this tool."


def test_nonexistent_group_operations(comprehensive_setup):
    """Test operations on nonexistent groups."""
    commands = [
        "modify group sztest_nonexistent_group --add-users sztest_comp_user1 --json",
        "delete group sztest_nonexistent_group --json"
    ]
    for cmd in commands:
        result = run_smb_zfs_command(cmd)
        assert result == "Error: Group 'sztest_nonexistent_group' not found or not managed by this tool."


def test_nonexistent_share_operations(comprehensive_setup):
    """Test operations on nonexistent shares."""
    commands = [
        "modify share nonexistent_share --comment 'New comment' --json",
        "delete share nonexistent_share --yes --json"
    ]
    for cmd in commands:
        result = run_smb_zfs_command(cmd)
        assert result == "Error: Share 'nonexistent_share' not found or not managed by this tool."


# --- Complex Scenario Tests ---
def test_user_with_multiple_groups(comprehensive_setup):
    """Test user membership in multiple groups."""
    # Add user to multiple groups
    run_smb_zfs_command(
        "modify group sztest_comp_group1 --add-users sztest_comp_user3 --json")
    run_smb_zfs_command(
        "modify group sztest_comp_group2 --add-users sztest_comp_user3 --json")

    user_details = get_system_user_details('sztest_comp_user3')
    assert 'sztest_comp_group1' in user_details
    assert 'sztest_comp_group2' in user_details


def test_share_with_complex_permissions(comprehensive_setup):
    """Test creating and modifying shares with complex permission sets."""
    # Create share with mixed user and group permissions
    run_smb_zfs_command(
        "create share complex_share --dataset shares/complex_share --valid-users sztest_comp_user1,@sztest_comp_group1,sztest_comp_user3 --owner sztest_comp_user1 --group sztest_comp_group1 --perms 770 --json")

    state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert 'complex_share' in state['shares']
    assert 'sztest_comp_user1' in state['shares']['complex_share']['smb_config']['valid_users']
    assert '@sztest_comp_group1' in state['shares']['complex_share']['smb_config']['valid_users']
    assert 'sztest_comp_user3' in state['shares']['complex_share']['smb_config']['valid_users']


def test_quota_operations(comprehensive_setup):
    """Test various quota operations."""
    # Set quota
    run_smb_zfs_command("modify home sztest_comp_user1 --quota 15G --json")
    assert get_zfs_property(
        'primary_testpool/homes/sztest_comp_user1', 'quota') == '15G'

    # Change quota
    run_smb_zfs_command("modify home sztest_comp_user1 --quota 25G --json")
    assert get_zfs_property(
        'primary_testpool/homes/sztest_comp_user1', 'quota') == '25G'

    # Remove quota
    run_smb_zfs_command("modify home sztest_comp_user1 --quota none --json")
    assert get_zfs_property(
        'primary_testpool/homes/sztest_comp_user1', 'quota') == 'none'


def test_share_quota_operations(comprehensive_setup):
    """Test share quota operations."""
    # Modify existing share quota
    run_smb_zfs_command("modify share comp_share2 --quota 100G --json")
    assert get_zfs_property(
        'secondary_testpool/shares/comp_share2', 'quota') == '100G'

    # Remove share quota
    run_smb_zfs_command("modify share comp_share2 --quota none --json")
    assert get_zfs_property(
        'secondary_testpool/shares/comp_share2', 'quota') == 'none'


# --- Comprehensive Modify Tests ---
def test_modify_share_all_options(comprehensive_setup):
    """Test modifying all possible share options."""
    # Create a basic share
    result = run_smb_zfs_command(
        "create share modify_all --dataset shares/modify_all --json")
    assert 'Error' not in result
    assert type(result) == dict
    assert 'msg' in result
    assert 'state' in result
    assert "Share 'modify_all' created successfully."

    # Modify all possible options
    result = run_smb_zfs_command(
        "modify share modify_all --pool secondary_testpool --name modify_all_renamed --comment 'Fully modified share' --valid-users sztest_comp_user1,sztest_comp_user2 --owner sztest_comp_user1 --group sztest_comp_group1 --perms 755 --quota 30G --readonly --no-browse --json")
    assert 'Error' not in result
    assert type(result) == dict
    assert 'msg' in result
    assert 'state' in result
    assert "Share 'modify_all' modified successfully."
    
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
    assert get_zfs_property(
        'secondary_testpool/shares/modify_all_renamed', 'type') == 'filesystem'
    assert get_zfs_property(
        'primary_testpool/shares/modify_all_renamed', 'type') is None
    assert get_zfs_property(
        'secondary_testpool/shares/modify_all_renamed', 'quota') == '30G'
    
    # Check Filesystem
    assert 755 == get_file_permissions(get_zfs_property('secondary_testpool/shares/modify_all_renamed', 'mountpoint'))
    owner, group = get_owner_and_group(get_zfs_property('secondary_testpool/shares/modify_all_renamed', 'mountpoint'))
    assert owner == 'sztest_comp_user1'
    assert group == 'sztest_comp_group1'

    # Check smb.conf
    assert '[modify_all_renamed]' in smb_conf
    assert 'valid users = sztest_comp_user1,sztest_comp_user2' in smb_conf
    assert 'read only = yes' in smb_conf
    assert 'browseable = yes' in smb_conf


def test_modify_setup_all_options(comprehensive_setup):
    """Test modifying all setup options."""
    # Test all setup modification options
    run_smb_zfs_command(
        "modify setup --server-name FULLTEST --workgroup FULLGROUP --macos --default-home-quota 40G --json")

    state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert state['server_name'] == 'FULLTEST'
    assert state['workgroup'] == 'FULLGROUP'
    assert 'server string = FULLTEST' in smb_conf
    assert 'workgroup = FULLGROUP' in smb_conf


# --- List Command Tests ---
def test_list_command_outputs(comprehensive_setup):
    """Test that list commands produce expected output format."""
    # Test list users
    users_output = run_smb_zfs_command("list users")
    assert 'sztest_comp_user1' in users_output
    assert 'sztest_comp_user2' in users_output
    assert 'sztest_comp_user3' in users_output

    # Test list groups
    groups_output = run_smb_zfs_command("list groups")
    assert 'sztest_comp_group1' in groups_output
    assert 'sztest_comp_group2' in groups_output

    # Test list shares
    shares_output = run_smb_zfs_command("list shares")
    assert 'comp_share1' in shares_output
    assert 'comp_share2' in shares_output

    # Test list pools
    pools_output = run_smb_zfs_command("list pools")
    assert 'primary_testpool' in pools_output
    assert 'secondary_testpool' in pools_output


def test_password_error_handling():
    """Test handling of empty or missing passwords."""
    result = run_smb_zfs_command(
        "create user sztest_test_user_123", [''])
    assert 'Password cannot be empty.' in result

    result = run_smb_zfs_command(
        "create user sztest_test_user_123", ['t'])
    assert "Password is not strong enough:" in result
    assert "- It must be at least 8 characters long." in result
    assert "- It must contain at least one digit." in result
    assert "- It must contain at least one uppercase letter." in result
    assert "- It must contain at least one symbol." in result

    result = run_smb_zfs_command(
        "create user sztest_test_user_123", ['T'])
    assert "Password is not strong enough:" in result
    assert "- It must be at least 8 characters long." in result
    assert "- It must contain at least one digit." in result
    assert "- It must contain at least one lowercase letter." in result
    assert "- It must contain at least one symbol." in result

    result = run_smb_zfs_command(
        "create user sztest_test_user_123", ['T1'])
    assert "Password is not strong enough:" in result
    assert "- It must be at least 8 characters long." in result
    assert "- It must contain at least one lowercase letter." in result
    assert "- It must contain at least one symbol." in result

    result = run_smb_zfs_command(
        "create user sztest_test_user_123", ['T1e'])
    assert "Password is not strong enough:" in result
    assert "- It must be at least 8 characters long." in result
    assert "- It must contain at least one symbol." in result

    result = run_smb_zfs_command(
        "create user sztest_test_user_123", ['T1e$'])
    assert "Password is not strong enough:" in result
    assert "- It must be at least 8 characters long." in result

    result = run_smb_zfs_command(
        "create user sztest_test_user_123", ['T1e$T1e$', 'A1e$T1e$'])
    assert "Passwords do not match. Please try again."


def test_special_characters_in_names(comprehensive_setup):
    """Test handling of special characters in names."""
    # Test with underscores and numbers (should work)
    run_smb_zfs_command(
        "create user sztest_test_user_123 --password 'TestPass!' --json")
    run_smb_zfs_command(
        "create group sztest_test_group_456 --description 'Test group with numbers' --json")

    state = run_smb_zfs_command("get-state")
    assert 'sztest_test_user_123' in state['users']
    assert 'sztest_test_group_456' in state['groups']


def test_long_descriptions_and_comments(comprehensive_setup):
    """Test handling of long descriptions and comments."""
    long_description = "This is a very long description that contains many words and should test the handling of lengthy text in group descriptions and share comments."

    run_smb_zfs_command(
        f"create group sztest_long_desc_group --description '{long_description}' --json")
    run_smb_zfs_command(
        f"create share long_comment_share --dataset shares/long_comment_share --comment '{long_description}' --json")

    state = run_smb_zfs_command("get-state")
    assert state['groups']['sztest_long_desc_group']['description'] == long_description
    assert state['shares']['long_comment_share']['smb_config']['comment'] == long_description


# --- State Consistency Tests ---
def test_state_consistency_after_operations(comprehensive_setup):
    """Test that state remains consistent after various operations."""
    initial_state = run_smb_zfs_command("get-state")

    # Perform various operations
    run_smb_zfs_command(
        "create user sztest_state_test --password 'StateTest!' --json")
    run_smb_zfs_command(
        "modify group sztest_comp_group1 --add-users sztest_state_test --json")
    run_smb_zfs_command(
        "create share state_share --dataset shares/state_share --valid-users sztest_state_test --json")

    final_state = run_smb_zfs_command("get-state")

    # Verify state consistency
    assert 'sztest_state_test' in final_state['users']
    assert 'state_share' in final_state['shares']
    assert len(final_state['users']) == len(initial_state['users']) + 1
    assert len(final_state['shares']) == len(
        initial_state['shares']) + 1


def test_cleanup_operations(comprehensive_setup):
    """Test that cleanup operations work correctly."""
    # Create temporary resources
    run_smb_zfs_command(
        "create user sztest_cleanup_user --password 'CleanupPass!' --json")
    run_smb_zfs_command("create group sztest_cleanup_group --json")
    run_smb_zfs_command(
        "create share cleanup_share --dataset shares/cleanup_share --json")

    # Verify they exist
    state = run_smb_zfs_command("get-state")
    assert 'sztest_cleanup_user' in state['users']
    assert 'sztest_cleanup_group' in state['groups']
    assert 'cleanup_share' in state['shares']

    # Clean them up
    run_smb_zfs_command("delete user sztest_cleanup_user --delete-data --yes --json")
    run_smb_zfs_command("delete group sztest_cleanup_group --json")
    run_smb_zfs_command(
        "delete share cleanup_share --delete-data --yes --json")

    # Verify they're gone
    final_state = run_smb_zfs_command("get-state")
    assert 'sztest_cleanup_user' not in final_state['users']
    assert 'sztest_cleanup_group' not in final_state['groups']
    assert 'cleanup_share' not in final_state['shares']
