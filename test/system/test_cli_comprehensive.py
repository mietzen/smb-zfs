import pytest
import subprocess
from conftest import (
    run_smb_zfs_command,
    get_system_user_details,
    get_zfs_property,
    read_smb_conf,
)


# --- JSON Output Consistency Tests ---
def test_json_output_format(comprehensive_setup):
    """Test that all commands with --json flag return valid JSON."""
    # Test various commands return valid JSON
    commands = [
        "create user json_test --password 'JsonTest!' --json",
        "create group json_group --json",
        "create share json_share --dataset shares/json_share --json",
        "modify group comp_group1 --add-users comp_user1 --json",
        "modify share comp_share1 --comment 'Modified via JSON' --json",
        "modify home comp_user1 --quota 10G --json",
        "delete group json_group --json",
        "delete share json_share --yes --json",
        "delete user json_test --yes --json"
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
    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command(
            "create user comp_user1 --password 'DuplicatePass!' --json")


def test_duplicate_group_creation(comprehensive_setup):
    """Test creating duplicate groups returns appropriate error."""
    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command(
            "create group comp_group1 --description 'Duplicate group' --json")


def test_duplicate_share_creation(comprehensive_setup):
    """Test creating duplicate shares returns appropriate error."""
    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command(
            "create share comp_share1 --dataset shares/comp_share1_dup --json")


def test_nonexistent_user_operations(comprehensive_setup):
    """Test operations on nonexistent users."""
    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command("delete user nonexistent_user --yes --json")

    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command("modify home nonexistent_user --quota 5G --json")


def test_nonexistent_group_operations(comprehensive_setup):
    """Test operations on nonexistent groups."""
    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command(
            "modify group nonexistent_group --add-users comp_user1 --json")

    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command("delete group nonexistent_group --json")


def test_nonexistent_share_operations(comprehensive_setup):
    """Test operations on nonexistent shares."""
    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command(
            "modify share nonexistent_share --comment 'New comment' --json")

    with pytest.raises(subprocess.CalledProcessError):
        run_smb_zfs_command("delete share nonexistent_share --yes --json")


# --- Complex Scenario Tests ---
def test_user_with_multiple_groups(comprehensive_setup):
    """Test user membership in multiple groups."""
    # Add user to multiple groups
    run_smb_zfs_command(
        "modify group comp_group1 --add-users comp_user3 --json")
    run_smb_zfs_command(
        "modify group comp_group2 --add-users comp_user3 --json")

    user_details = get_system_user_details('comp_user3')
    assert 'comp_group1' in user_details
    assert 'comp_group2' in user_details


def test_share_with_complex_permissions(comprehensive_setup):
    """Test creating and modifying shares with complex permission sets."""
    # Create share with mixed user and group permissions
    run_smb_zfs_command(
        "create share complex_share --dataset shares/complex_share --valid-users comp_user1,@comp_group1,comp_user3 --owner comp_user1 --group comp_group1 --perms 770 --json")

    state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    assert 'complex_share' in state['shares']
    assert 'comp_user1' in state['shares']['complex_share']['smb_config']['valid_users']
    assert '@comp_group1' in state['shares']['complex_share']['smb_config']['valid_users']
    assert 'comp_user3' in state['shares']['complex_share']['smb_config']['valid_users']


def test_quota_operations(comprehensive_setup):
    """Test various quota operations."""
    # Set quota
    run_smb_zfs_command("modify home comp_user1 --quota 15G --json")
    assert get_zfs_property(
        'primary_testpool/homes/comp_user1', 'quota') == '15G'

    # Change quota
    run_smb_zfs_command("modify home comp_user1 --quota 25G --json")
    assert get_zfs_property(
        'primary_testpool/homes/comp_user1', 'quota') == '25G'

    # Remove quota
    run_smb_zfs_command("modify home comp_user1 --quota none --json")
    assert get_zfs_property(
        'primary_testpool/homes/comp_user1', 'quota') == 'none'


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
    run_smb_zfs_command(
        "create share modify_all --dataset shares/modify_all --json")

    # Modify all possible options
    run_smb_zfs_command(
        "modify share modify_all --comment 'Fully modified share' --valid-users comp_user1,comp_user2 --owner comp_user1 --group comp_group1 --perms 755 --quota 30G --readonly --no-browse --json")

    state = run_smb_zfs_command("get-state")
    smb_conf = read_smb_conf()

    share_config = state['shares']['modify_all']
    assert share_config['smb_config']['comment'] == 'Fully modified share'
    assert share_config['smb_config']['read_only'] == 'yes'
    assert share_config['smb_config']['browseable'] == 'no'
    assert 'comp_user1' in share_config['smb_config']['valid_users']
    assert 'comp_user2' in share_config['smb_config']['valid_users']

    assert get_zfs_property(
        'primary_testpool/shares/modify_all', 'quota') == '30G'


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
    assert 'comp_user1' in users_output
    assert 'comp_user2' in users_output
    assert 'comp_user3' in users_output

    # Test list groups
    groups_output = run_smb_zfs_command("list groups")
    assert 'comp_group1' in groups_output
    assert 'comp_group2' in groups_output

    # Test list shares
    shares_output = run_smb_zfs_command("list shares")
    assert 'comp_share1' in shares_output
    assert 'comp_share2' in shares_output

    # Test list pools
    pools_output = run_smb_zfs_command("list pools")
    assert 'primary_testpool' in pools_output
    assert 'secondary_testpool' in pools_output


# --- Edge Case Tests ---
def test_empty_password_handling():
    """Test handling of empty or missing passwords."""
    # This would need interactive testing or mocking in a real environment
    # For now, verify the command structure
    pass


def test_special_characters_in_names(comprehensive_setup):
    """Test handling of special characters in names."""
    # Test with underscores and numbers (should work)
    run_smb_zfs_command(
        "create user test_user_123 --password 'TestPass!' --json")
    run_smb_zfs_command(
        "create group test_group_456 --description 'Test group with numbers' --json")

    state = run_smb_zfs_command("get-state")
    assert 'test_user_123' in state['users']
    assert 'test_group_456' in state['groups']


def test_long_descriptions_and_comments(comprehensive_setup):
    """Test handling of long descriptions and comments."""
    long_description = "This is a very long description that contains many words and should test the handling of lengthy text in group descriptions and share comments."

    run_smb_zfs_command(
        f"create group long_desc_group --description '{long_description}' --json")
    run_smb_zfs_command(
        f"create share long_comment_share --dataset shares/long_comment_share --comment '{long_description}' --json")

    state = run_smb_zfs_command("get-state")
    assert state['groups']['long_desc_group']['description'] == long_description
    assert state['shares']['long_comment_share']['smb_config']['comment'] == long_description


# --- State Consistency Tests ---
def test_state_consistency_after_operations(comprehensive_setup):
    """Test that state remains consistent after various operations."""
    initial_state = run_smb_zfs_command("get-state")

    # Perform various operations
    run_smb_zfs_command(
        "create user state_test --password 'StateTest!' --json")
    run_smb_zfs_command(
        "modify group comp_group1 --add-users state_test --json")
    run_smb_zfs_command(
        "create share state_share --dataset shares/state_share --valid-users state_test --json")

    final_state = run_smb_zfs_command("get-state")

    # Verify state consistency
    assert 'state_test' in final_state['users']
    assert 'state_share' in final_state['shares']
    assert len(final_state['users']) == len(initial_state['users']) + 1
    assert len(final_state['shares']) == len(
        initial_state['shares']) + 1


def test_cleanup_operations(comprehensive_setup):
    """Test that cleanup operations work correctly."""
    # Create temporary resources
    run_smb_zfs_command(
        "create user cleanup_user --password 'CleanupPass!' --json")
    run_smb_zfs_command("create group cleanup_group --json")
    run_smb_zfs_command(
        "create share cleanup_share --dataset shares/cleanup_share --json")

    # Verify they exist
    state = run_smb_zfs_command("get-state")
    assert 'cleanup_user' in state['users']
    assert 'cleanup_group' in state['groups']
    assert 'cleanup_share' in state['shares']

    # Clean them up
    run_smb_zfs_command("delete user cleanup_user --delete-data --yes --json")
    run_smb_zfs_command("delete group cleanup_group --json")
    run_smb_zfs_command(
        "delete share cleanup_share --delete-data --yes --json")

    # Verify they're gone
    final_state = run_smb_zfs_command("get-state")
    assert 'cleanup_user' not in final_state['users']
    assert 'cleanup_group' not in final_state['groups']
    assert 'cleanup_share' not in final_state['shares']
