import subprocess
import pwd
import grp

from . import SmbZfsError, SMB_CONF


class System:
    """A helper class for executing system commands."""

    def _run(self, command, input_data=None, check=True):
        try:
            process = subprocess.run(
                command,
                input=input_data,
                capture_output=True,
                text=True,
                check=check,
            )
            return process
        except FileNotFoundError as e:
            raise SmbZfsError(f"Command not found: {e.filename}") from e
        except subprocess.CalledProcessError as e:
            error_message = (
                f"Command '{' '.join(e.cmd)}' failed with exit code {e.returncode}.\n"
                f"Stderr: {e.stderr.strip()}"
            )
            raise SmbZfsError(error_message) from e

    def user_exists(self, username):
        try:
            pwd.getpwnam(username)
            return True
        except KeyError:
            return False

    def group_exists(self, groupname):
        try:
            grp.getgrnam(groupname)
            return True
        except KeyError:
            return False

    def add_system_user(self, username, home_dir=None, shell=None):
        cmd = ["useradd"]
        if home_dir:
            cmd.extend(["-d", home_dir, "-m"])
        else:
            cmd.append("-M")
        if shell:
            cmd.extend(["-s", shell])
        else:
            cmd.extend(["-s", "/usr/sbin/nologin"])
        cmd.append(username)
        self._run(cmd)

    def delete_system_user(self, username):
        self._run(["userdel", username])

    def add_system_group(self, groupname):
        self._run(["groupadd", groupname])

    def delete_system_group(self, groupname):
        self._run(["groupdel", groupname])

    def add_user_to_group(self, username, groupname):
        self._run(["usermod", "-a", "-G", groupname, username])

    def remove_user_from_group(self, username, groupname):
        self._run(["gpasswd", "-d", username, groupname])

    def set_system_password(self, username, password):
        self._run(["chpasswd"], input_data=f"{username}:{password}")

    def add_samba_user(self, username, password):
        self._run(
            ["smbpasswd", "-a", "-s", username], input_data=f"{password}\n{password}"
        )
        self._run(["smbpasswd", "-e", username])

    def delete_samba_user(self, username):
        if self.samba_user_exists(username):
            self._run(["smbpasswd", "-x", username])

    def samba_user_exists(self, username):
        result = self._run(["pdbedit", "-L"])
        return f"{username}:" in result.stdout

    def set_samba_password(self, username, password):
        self._run(["smbpasswd", "-s", username], input_data=f"{password}\n{password}")

    def test_samba_config(self):
        self._run(["testparm", "-s", SMB_CONF])

    def reload_samba(self):
        self._run(["systemctl", "reload", "smbd", "nmbd"])

    def restart_services(self):
        self._run(["systemctl", "restart", "smbd", "nmbd", "avahi-daemon"])

    def enable_services(self):
        self._run(["systemctl", "enable", "smbd", "nmbd", "avahi-daemon"])

    def stop_services(self):
        self._run(["systemctl", "stop", "smbd", "nmbd", "avahi-daemon"], check=False)

    def disable_services(self):
        self._run(["systemctl", "disable", "smbd", "nmbd", "avahi-daemon"], check=False)

    def apt_update(self):
        self._run(["apt-get", "update"])

    def apt_install(self, packages):
        cmd = ["apt-get", "install", "-y"]
        cmd.extend(packages)
        self._run(cmd)

    def apt_purge(self, packages):
        cmd = ["apt-get", "purge", "-y", "--auto-remove"]
        cmd.extend(packages)
        self._run(cmd)
