import grp
import pwd
import subprocess
import os
import sys
from typing import List, Optional

from .errors import SmbZfsError
from .const import SMB_CONF


class System:
    def _run(self, command: List[str], input_data: Optional[str] = None, check: bool = True) -> subprocess.CompletedProcess:
        """Executes a system command."""
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
                if i > 0:
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
        result = self._run(
            ["dpkg-query", "--show",
                "--showformat=${db:Status-Status}", package_name],
            check=False
        )
        return result.returncode == 0 and result.stdout.strip() == "installed"

    def user_exists(self, username: str) -> bool:
        """Checks if a system user exists."""
        try:
            pwd.getpwnam(username)
            return True
        except KeyError:
            return False

    def group_exists(self, groupname: str) -> bool:
        """Checks if a system group exists."""
        try:
            grp.getgrnam(groupname)
            return True
        except KeyError:
            return False

    def add_system_user(self, username: str, home_dir: Optional[str] = None, shell: Optional[str] = None) -> None:
        """Adds a system user idempotently."""
        if self.user_exists(username):
            return
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
            self._run(["userdel", username])

    def add_system_group(self, groupname: str) -> None:
        """Adds a system group idempotently."""
        if not self.group_exists(groupname):
            self._run(["groupadd", groupname])

    def delete_system_group(self, groupname: str) -> None:
        """Deletes a system group idempotently."""
        if self.group_exists(groupname):
            self._run(["groupdel", groupname])

    def add_user_to_group(self, username: str, groupname: str) -> None:
        """Adds a user to a system group."""
        self._run(["usermod", "-a", "-G", groupname, username])

    def remove_user_from_group(self, username: str, groupname: str) -> None:
        """Removes a user from a system group."""
        self._run(["gpasswd", "-d", username, groupname])

    def set_system_password(self, username: str, password: str) -> None:
        """Sets a user's system password via chpasswd."""
        self._run(["chpasswd"], input_data=f"{username}:{password}")

    def add_samba_user(self, username: str, password: str) -> None:
        """Adds a new Samba user."""
        self._run(
            ["smbpasswd", "-a", "-s", username], input_data=f"{password}\n{password}"
        )
        self._run(["smbpasswd", "-e", username])

    def delete_samba_user(self, username: str) -> None:
        """Deletes a Samba user idempotently."""
        if self.samba_user_exists(username):
            self._run(["smbpasswd", "-x", username])

    def samba_user_exists(self, username: str) -> bool:
        """Checks if a Samba user exists in the database."""
        result = self._run(["pdbedit", "-L", "-u", username], check=False)
        return result.returncode == 0

    def set_samba_password(self, username: str, password: str) -> None:
        """Sets a Samba user's password."""
        self._run(["smbpasswd", "-s", username],
                  input_data=f"{password}\n{password}")

    def test_samba_config(self) -> None:
        """Tests the Samba configuration file for syntax errors."""
        self._run(["testparm", "-s", SMB_CONF])

    def reload_samba(self) -> None:
        """Reloads the Samba service configuration."""
        self._run(["systemctl", "reload", "smbd", "nmbd"])

    def restart_services(self) -> None:
        """Restarts core networking and file sharing services."""
        self._run(["systemctl", "restart", "smbd", "nmbd", "avahi-daemon"])

    def enable_services(self) -> None:
        """Enables core services to start on boot."""
        self._run(["systemctl", "enable", "smbd", "nmbd", "avahi-daemon"])

    def stop_services(self) -> None:
        """Stops core services."""
        self._run(["systemctl", "stop", "smbd",
                  "nmbd", "avahi-daemon"], check=False)

    def disable_services(self) -> None:
        """Disables core services from starting on boot."""
        self._run(["systemctl", "disable", "smbd",
                  "nmbd", "avahi-daemon"], check=False)

    def delete_gracefully(self, f) -> None:
        """Attempts to delete the specified file gracefully. Prints a warning if a removal wasn't possible."""
        if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError as e:
                    print(f"Warning: could not remove file {f}: {e}")
