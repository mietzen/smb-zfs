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