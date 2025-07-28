import pwd
import grp
import io
import json
import os
import pytest
import shlex
import subprocess
from smb_zfs.cli import main as cli
from smb_zfs.smb_zfs import STATE_FILE, SMB_CONF
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr


def run_smb_zfs_command(command):
    """Helper function to run smb-zfs commands."""
    # The get-state command always returns JSON without a flag.
    is_json_output = "--json" in command or command.strip().startswith("get-state")

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    # Redirect stdout and stderr
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            with patch("sys.argv", ['smb-zfs'] + shlex.split(command)):
                cli()
        except SystemExit:
            # argparse may call sys.exit(), especially on errors or --help
            pass

    stdout = stdout_buffer.getvalue()
    stderr = stderr_buffer.getvalue()
    if stderr:
        return format_text_output(f'{stdout}\n\n{stderr}')

    if is_json_output:
        # Handle cases where stdout might be empty on success (e.g., some --json commands)
        if not stdout.strip():
            return {}
        return json.loads(stdout)

    return format_text_output(stdout)


def format_text_output(text: str) -> str:
    """Format as multiline string and remove leading / trailing whitespaces"""
    return '\n'.join(line.strip() for line in text.strip().splitlines())


def get_system_user_details(username):
    """Get details for a system user."""
    try:
        result = subprocess.run(
            f"id {username}",
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def get_system_user_shell(username):
    """Get shell for a system user."""
    try:
        result = subprocess.run(
            f"getent passwd {username} " + "| awk -F: '{print $NF}'",
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def get_system_user_exists(username):
    """Check if a system user exists."""
    try:
        subprocess.run(
            f"getent passwd {username}",
            shell=True,
            check=True,
            capture_output=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_system_group_exists(groupname):
    """Check if a system group exists."""
    try:
        subprocess.run(
            f"getent group {groupname}",
            shell=True,
            check=True,
            capture_output=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_zfs_property(dataset, prop):
    """Get a specific ZFS property."""
    try:
        result = subprocess.run(
            f"zfs get -H -o value {prop} {dataset}",
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_zfs_dataset_exists(dataset):
    """Check if a ZFS dataset exists."""
    try:
        subprocess.run(
            f"zfs list {dataset}",
            shell=True,
            check=True,
            capture_output=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_zfs_dataset(pool):
    """Check if a ZFS dataset exists."""
    result = subprocess.run(
        ["zfs", "list", "-H", "-o", "name", "-r", pool],
        check=True,
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    return result.stdout.strip().splitlines()[1:]


def read_smb_conf():
    """Read the contents of the smb.conf file."""
    try:
        with open('/etc/samba/smb.conf', 'r') as f:
            return f.read()
    except FileNotFoundError:
        return ""


@pytest.fixture(autouse=True)
def manage_smb_zfs_environment():
    """Fixture to set up and tear down smb-zfs for each test."""
    # Setup: Ensure a clean state before setting up
    try:
        run_smb_zfs_command(
            "setup --primary-pool primary_testpool --secondary-pools secondary_testpool tertiary_testpool --server-name TESTSERVER --workgroup TESTGROUP")
        yield
        run_smb_zfs_command("remove --delete-users --delete-data --yes")
    finally:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        if os.path.exists(SMB_CONF):
            os.remove(SMB_CONF)
        cleanup_test_datasets([
            "primary_testpool",
            "secondary_testpool",
            "tertiary_testpool",
        ])
        cleanup_test_users_and_groups("sztest_")


def cleanup_test_users_and_groups(prefix):
    # Delete users starting with prefix
    for user in pwd.getpwall():
        if user.pw_name.startswith(prefix):
            subprocess.run(["userdel", "-r", user.pw_name], check=True)

    # Delete groups starting with prefix
    for group in grp.getgrall():
        if group.gr_name.startswith(prefix):
            subprocess.run(["groupdel", group.gr_name], check=True)


def cleanup_test_datasets(pools):
    for pool in pools:
        # Use -r to recursively destroy all datasets
        subprocess.run(
            ["zfs", "destroy", "-r", pool], check=True)


@pytest.fixture
def initial_state():
    """Fixture to get the state of the system before a test action."""
    return run_smb_zfs_command("get-state")


@pytest.fixture
def basic_users_and_groups():
    """Fixture to create basic users and groups for testing."""
    run_smb_zfs_command("create user sztest_user_a --password 'PassA!' --json")
    run_smb_zfs_command("create user sztest_user_b --password 'PassB!' --json")
    run_smb_zfs_command("create user sztest_user_c --password 'PassC!' --json")
    run_smb_zfs_command(
        "create group sztest_test_group --description 'A test group' --json")


@pytest.fixture
def comprehensive_setup():
    """Fixture to create a comprehensive test environment."""
    # Create users
    run_smb_zfs_command(
        "create user sztest_comp_user1 --password 'CompPass1!' --shell --json")
    run_smb_zfs_command(
        "create user sztest_comp_user2 --password 'CompPass2!' --json")
    run_smb_zfs_command(
        "create user sztest_comp_user3 --password 'CompPass3!' --no-home --json")

    # Create groups
    run_smb_zfs_command(
        "create group sztest_comp_group1 --description 'Comprehensive group 1' --json")
    run_smb_zfs_command(
        "create group sztest_comp_group2 --description 'Comprehensive group 2' --users sztest_comp_user1,sztest_comp_user2 --json")

    # Create shares
    run_smb_zfs_command(
        "create share comp_share1 --dataset shares/comp_share1 --comment 'Comprehensive share 1' --json")
    run_smb_zfs_command(
        "create share comp_share2 --dataset shares/comp_share2 --pool secondary_testpool --valid-users sztest_comp_user1,@sztest_comp_group1 --readonly --quota 50G --json")
