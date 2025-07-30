import grp
import pwd
import subprocess
import os
import logging
from typing import List, Optional

from .errors import SmbZfsError
from .const import SMB_CONF

# --- Logger Setup ---
logger = logging.getLogger(__name__)


class System:
    """A helper class for system-level operations and command execution."""

    def _run(self, command: List[str], input_data: Optional[str] = None, check: bool = True) -> subprocess.CompletedProcess:
        """Executes a system command."""
        logger.debug("Running command: %s", " ".join(command))
        try:
            return subprocess.run(
                command,
                input=input_data,
                capture_output=True,
                text=True,
                check=check,
                shell=False
            )
        except FileNotFoundError as e:
            raise SmbZfsError(f"Command not found: {e.filename}") from e
        except subprocess.CalledProcessError as e:
            error_message = (
                f"Command '{' '.join(e.cmd)}' failed with exit code {e.returncode}.\n"
                f"Stderr: {e.stderr.strip() if e.stderr else ''}"
            )
            raise SmbZfsError(error_message) from e

    def _run_piped(self, commands: List[List[str]]) -> subprocess.CompletedProcess:
        """Executes a series of piped commands safely."""
        logger.debug("Running piped commands: %s", " | ".join([" ".join(cmd) for cmd in commands]))
        try:
            procs = []
            stdin_stream = None
            for i, cmd in enumerate(commands):
                proc = subprocess.Popen(
                    cmd,
                    stdin=stdin_stream,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                procs.append(proc)
                if i > 0 and procs[i-1].stdout:
                    procs[i-1].stdout.close()
                stdin_stream = proc.stdout

            last_proc = procs[-1]
            stdout, stderr = last_proc.communicate()

            for proc in procs:
                proc.wait()
                if proc.returncode != 0:
                    raise SmbZfsError(
                        f"Command '{' '.join(proc.args)}' failed with exit code {proc.returncode}.\n"
                        f"Final Stderr: {stderr.strip()}"
                    )

            return subprocess.CompletedProcess(
                args=last_proc.args,
                returncode=last_proc.returncode,
                stdout=stdout,
                stderr=stderr
            )
        except FileNotFoundError as e:
            raise SmbZfsError(f"Command not found: {e.filename}") from e

    def is_package_installed(self, package_name: str) -> bool:
        """Checks if a Debian package is installed."""
        logger.debug("Checking if package '%s' is installed.", package_name)
        result = self._run(
            ["dpkg-query", "--show",
                "--showformat=${db:Status-Status}", package_name],
            check=False
        )
        return result.returncode == 0 and result.stdout.strip() == "installed"

    def user_exists(self, username: str) -> bool:
        """Checks if a system user exists."""
        logger.debug("Checking if system user '%s' exists.", username)
        try:
            pwd.getpwnam(username)
            return True
        except KeyError:
            return False

    def group_exists(self, groupname: str) -> bool:
        """Checks if a system group exists."""
        logger.debug("Checking if system group '%s' exists.", groupname)
        try:
            grp.getgrnam(groupname)
            return True
        except KeyError:
            return False

    def add_system_user(self, username: str, home_dir: Optional[str] = None, shell: Optional[str] = None) -> None:
        """Adds a system user idempotently."""
        if self.user_exists(username):
            logger.debug("System user '%s' already exists, skipping creation.", username)
            return
        logger.info("Adding system user '%s'.", username)
        cmd = ["useradd"]
        if home_dir:
            cmd.extend(["-d", home_dir, "-m"])
        else:
            cmd.append("-M")
        cmd.extend(["-s", shell or "/usr/sbin/nologin"])
        cmd.append(username)
        self._run(cmd)

    def delete_system_user(self, username: str) -> None:
        """Deletes a system user idempotently."""
        if self.user_exists(username):
            logger.info("Deleting system user '%s'.", username)
            self._run(["userdel", username])
        else:
            logger.debug("System user '%s' does not exist, skipping deletion.", username)

    def add_system_group(self, groupname: str) -> None:
        """Adds a system group idempotently."""
        if not self.group_exists(groupname):
            logger.info("Adding system group '%s'.", groupname)
            self._run(["groupadd", groupname])
        else:
            logger.debug("System group '%s' already exists, skipping creation.", groupname)

    def delete_system_group(self, groupname: str) -> None:
        """Deletes a system group idempotently."""
        if self.group_exists(groupname):
            logger.info("Deleting system group '%s'.", groupname)
            self._run(["groupdel", groupname])
        else:
            logger.debug("System group '%s' does not exist, skipping deletion.", groupname)

    def add_user_to_group(self, username: str, groupname: str) -> None:
        """Adds a user to a system group."""
        logger.info("Adding user '%s' to group '%s'.", username, groupname)
        self._run(["usermod", "-a", "-G", groupname, username])

    def remove_user_from_group(self, username: str, groupname: str) -> None:
        """Removes a user from a system group."""
        logger.info("Removing user '%s' from group '%s'.", username, groupname)
        self._run(["gpasswd", "-d", username, groupname])

    def set_system_password(self, username: str, password: str) -> None:
        """Sets a user's system password via chpasswd."""
        logger.info("Setting system password for user '%s'.", username)
        self._run(["chpasswd"], input_data=f"{username}:{password}")

    def add_samba_user(self, username: str, password: str) -> None:
        """Adds a new Samba user."""
        logger.info("Adding Samba user '%s'.", username)
        self._run(
            ["smbpasswd", "-a", "-s", username], input_data=f"{password}\n{password}"
        )
        self._run(["smbpasswd", "-e", username])

    def delete_samba_user(self, username: str) -> None:
        """Deletes a Samba user idempotently."""
        if self.samba_user_exists(username):
            logger.info("Deleting Samba user '%s'.", username)
            self._run(["smbpasswd", "-x", username])
        else:
            logger.debug("Samba user '%s' does not exist, skipping deletion.", username)

    def samba_user_exists(self, username: str) -> bool:
        """Checks if a Samba user exists in the database."""
        logger.debug("Checking if Samba user '%s' exists.", username)
        result = self._run(["pdbedit", "-L", "-u", username], check=False)
        return result.returncode == 0

    def set_samba_password(self, username: str, password: str) -> None:
        """Sets a Samba user's password."""
        logger.info("Setting Samba password for user '%s'.", username)
        self._run(["smbpasswd", "-s", username],
                  input_data=f"{password}\n{password}")

    def test_samba_config(self) -> None:
        """Tests the Samba configuration file for syntax errors."""
        logger.info("Testing Samba configuration syntax.")
        self._run(["testparm", "-s", SMB_CONF])

    def reload_samba(self) -> None:
        """Reloads the Samba service configuration."""
        logger.info("Reloading Samba services (smbd, nmbd).")
        self._run(["systemctl", "reload", "smbd", "nmbd"])

    def restart_services(self) -> None:
        """Restarts core networking and file sharing services."""
        logger.info("Restarting services: smbd, nmbd, avahi-daemon.")
        self._run(["systemctl", "restart", "smbd", "nmbd", "avahi-daemon"])

    def enable_services(self) -> None:
        """Enables core services to start on boot."""
        logger.info("Enabling services to start on boot: smbd, nmbd, avahi-daemon.")
        self._run(["systemctl", "enable", "smbd", "nmbd", "avahi-daemon"])

    def stop_services(self) -> None:
        """Stops core services."""
        logger.info("Stopping services: smbd, nmbd, avahi-daemon.")
        self._run(["systemctl", "stop", "smbd",
                  "nmbd", "avahi-daemon"], check=False)

    def disable_services(self) -> None:
        """Disables core services from starting on boot."""
        logger.info("Disabling services from starting on boot: smbd, nmbd, avahi-daemon.")
        self._run(["systemctl", "disable", "smbd",
                  "nmbd", "avahi-daemon"], check=False)

    def delete_gracefully(self, f: str) -> None:
        """Attempts to delete the specified file gracefully."""
        if os.path.exists(f):
            logger.info("Attempting to delete file: %s", f)
            try:
                os.remove(f)
                logger.info("Successfully deleted file: %s", f)
            except OSError as e:
                logger.warning("Could not remove file %s: %s", f, e)
                print(f"Warning: could not remove file {f}: {e}")
        else:
            logger.debug("File '%s' does not exist, skipping deletion.", f)
