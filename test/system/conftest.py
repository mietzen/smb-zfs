import pytest
import subprocess
import json

def run_smb_zfs_command(command):
    """Helper function to run smb-zfs commands."""
    try:
        # The get-state command always returns JSON without a flag.
        is_json_output = "--json" in command or command.strip().startswith("get-state")

        result = subprocess.run(
            f"smb-zfs {command}",
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        if is_json_output:
            # Handle cases where stdout might be empty on success (e.g., some --json commands)
            if not result.stdout.strip():
                return {}
            return json.loads(result.stdout)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running command: smb-zfs {command}")
        print(f"Stderr: {e.stderr}")
        print(f"Stdout: {e.stdout}")
        raise


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
        # The 'remove' command correctly uses '--yes'
        run_smb_zfs_command("remove --delete-users --delete-data --yes")
    except subprocess.CalledProcessError:
        # Ignore errors if it's already clean
        pass

    # Setup smb-zfs. The 'setup' command does not have a '--yes' flag.
    run_smb_zfs_command("setup --primary-pool primary_testpool --secondary-pools secondary_testpool tertiary_testpool --server-name TESTSERVER --workgroup TESTGROUP")

    yield

    # Teardown: Clean up completely after each test
    run_smb_zfs_command("remove --delete-users --delete-data --yes")


@pytest.fixture
def initial_state():
    """Fixture to get the state of the system before a test action."""
    # get-state does not take a --json flag.
    return run_smb_zfs_command("get-state")


@pytest.fixture
def basic_users_and_groups():
    """Fixture to create basic users and groups for testing."""
    run_smb_zfs_command("create user user_a --password 'PassA!' --json")
    run_smb_zfs_command("create user user_b --password 'PassB!' --json")
    run_smb_zfs_command("create user user_c --password 'PassC!' --json")
    run_smb_zfs_command("create group test_group --description 'A test group' --json")


@pytest.fixture
def comprehensive_setup():
    """Fixture to create a comprehensive test environment."""
    # Create users
    run_smb_zfs_command("create user comp_user1 --password 'CompPass1!' --shell --json")
    run_smb_zfs_command("create user comp_user2 --password 'CompPass2!' --json")
    run_smb_zfs_command("create user comp_user3 --password 'CompPass3!' --no-home --json")

    # Create groups
    run_smb_zfs_command("create group comp_group1 --description 'Comprehensive group 1' --json")
    run_smb_zfs_command("create group comp_group2 --description 'Comprehensive group 2' --users comp_user1,comp_user2 --json")

    # Create shares
    run_smb_zfs_command("create share comp_share1 --dataset shares/comp_share1 --comment 'Comprehensive share 1' --json")
    run_smb_zfs_command("create share comp_share2 --dataset shares/comp_share2 --pool secondary_testpool --valid-users comp_user1,@comp_group1 --readonly --quota 50G --json")