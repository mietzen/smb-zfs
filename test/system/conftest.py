import pwd
import grp
import io
import json
import os
import stat
import pytest
import shlex
import subprocess
from smb_zfs.cli import main as cli
from smb_zfs.smb_zfs import STATE_FILE, SMB_CONF
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr
from smb_zfs.errors import SmbZfsError

def run_smb_zfs_command(command, user_inputs=None):
    """Helper function to run smb-zfs commands with optional user input."""
    is_json_output = "--json" in command or command.strip().startswith("get-state")

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    input_side_effect = user_inputs if isinstance(user_inputs, list) else [user_inputs] if user_inputs else []

    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        input_patch = patch("builtins.input", side_effect=input_side_effect)
        getpass_patch = patch("getpass.getpass", side_effect=input_side_effect)
        argv_patch = patch("sys.argv", ['smb-zfs'] + shlex.split(command))

        with argv_patch, input_patch, getpass_patch:
            try:
                cli()
            except SystemExit:
                pass

    stdout = stdout_buffer.getvalue()
    stderr = stderr_buffer.getvalue()

    if stderr:
        return format_text_output(f'{stdout}\n\n{stderr}')
    if is_json_output:
        return json.loads(stdout) if stdout.strip() else {}
    return format_text_output(stdout)


def check_wizard_output(result: str, expected_success_msg: str) -> None:
    """Checks the text output from a wizard session for a final success message."""
    assert isinstance(
        result, str), f"Expected text output from wizard, but got {type(result)}"
    # The final line of a successful wizard operation should contain the success message.
    last_line = result.strip().split('\n')[-1]
    assert f"Success: {expected_success_msg}" in last_line, \
        f"Wizard output did not contain the expected success message.\nOutput:\n{result}"


def check_smb_zfs_result(result, asserted_msg, json=False, is_error=False):
    """Checks the text output from a cli session."""
    assert asserted_msg
    if is_error:
        assert type(result) == str
        assert asserted_msg in result
    else:
        assert 'Error' not in result
        if json:
            assert type(result) == dict
            assert 'msg' in result
            assert 'state' in result
            assert asserted_msg in result['msg']
        else:
            assert type(result) == str
            assert asserted_msg in result
        

def format_text_output(text: str) -> str:
    """Format as multiline string and remove leading / trailing whitespaces"""
    return '\n'.join(line.strip() for line in text.strip().splitlines())


def get_file_permissions(path: str) -> int:
    """Returns file permissions in numeric form like 755 or 644"""
    mode = os.stat(path).st_mode
    perm = stat.S_IMODE(mode)
    return int(oct(perm)[-3:])

def get_owner_and_group(path: str) -> tuple[str, str]:
    """Returns the owner and group names of the file"""
    stat_info = os.stat(path)
    owner = pwd.getpwuid(stat_info.st_uid).pw_name
    group = grp.getgrgid(stat_info.st_gid).gr_name
    return owner, group


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
            f"getent passwd {username}",
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout.split(':')[-1].strip()
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
        result = run_smb_zfs_command(
            "setup --primary-pool primary_testpool --secondary-pools secondary_testpool tertiary_testpool --server-name TESTSERVER --workgroup TESTGROUP")
        if result != 'Setup completed successfully.':
            raise SmbZfsError(result)
        yield
    except Exception as e:
        raise(e)
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
