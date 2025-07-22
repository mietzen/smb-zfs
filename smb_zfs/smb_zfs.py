import os
import re
import pwd
import grp
from datetime import datetime

from . import (
    ConfigGenerator,
    StateManager,
    System,
    ZFS,
    SmbZfsError,
    STATE_FILE,
    SMB_CONF,
    AVAHI_SMB_SERVICE,
)


class SmbZfsManager:
    def __init__(self, state_path=STATE_FILE):
        self._system = System()
        self._zfs = ZFS(self._system)
        self._state = StateManager(state_path)
        self._config = ConfigGenerator()

    def _check_initialized(self):
        if not self._state.is_initialized():
            raise SmbZfsError("System not initialized. Run 'install' first.")

    def install(self, pool, server_name, workgroup, macos_optimized=False):
        if self._state.is_initialized():
            raise SmbZfsError("System is already initialized.")

        self._system.apt_update()
        self._system.apt_install(["samba", "samba-common-bin", "avahi-daemon"])

        self._zfs.create_dataset(f"{pool}/homes")
        homes_mountpoint = self._zfs.get_mountpoint(f"{pool}/homes")
        os.chmod(homes_mountpoint, 0o755)

        if not self._system.group_exists("smb_users"):
            self._system.add_system_group("smb_users")

        self._config.create_smb_conf(pool, server_name, workgroup, macos_optimized)
        self._config.create_avahi_conf()
        self._system.test_samba_config()
        self._system.enable_services()
        self._system.restart_services()

        self._state.set("initialized", True)
        self._state.set("zfs_pool", pool)
        self._state.set("server_name", server_name)
        self._state.set("workgroup", workgroup)
        self._state.set("macos_optimized", macos_optimized)

        self._state.set_item(
            "groups",
            "smb_users",
            {
                "description": "Samba Users Group",
                "members": [],
                "created": datetime.now(datetime.timezone.utc).isoformat(),
            },
        )
        return "Installation completed successfully."

    def create_user(self, username, password, allow_shell=False, groups=None):
        self._check_initialized()
        if self._state.get_item("users", username):
            raise SmbZfsError(f"User '{username}' is already managed by this tool.")
        if self._system.user_exists(username):
            raise SmbZfsError(f"System user '{username}' already exists.")

        pool = self._state.get("zfs_pool")
        home_dataset = f"{pool}/homes/{username}"
        home_mountpoint = self._zfs.get_mountpoint(home_dataset)

        self._system.add_system_user(
            username,
            home_dir=home_mountpoint if allow_shell else None,
            shell="/bin/bash" if allow_shell else "/usr/sbin/nologin",
        )

        self._zfs.create_dataset(home_dataset)
        os.chown(
            home_mountpoint,
            pwd.getpwnam(username).pw_uid,
            pwd.getpwnam(username).pw_gid,
        )
        os.chmod(home_mountpoint, 0o700)

        if allow_shell:
            self._system.set_system_password(username, password)

        self._system.add_samba_user(username, password)
        self._system.add_user_to_group(username, "smb_users")

        user_groups = []
        if groups:
            for group in groups:
                if self._state.get_item("groups", group):
                    self._system.add_user_to_group(username, group)
                    user_groups.append(group)

        user_config = {
            "shell_access": allow_shell,
            "home_dataset": home_dataset,
            "groups": user_groups,
            "created": datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._state.set_item("users", username, user_config)
        return f"User '{username}' created successfully."

    def delete_user(self, username, delete_data=False):
        self._check_initialized()
        user_info = self._state.get_item("users", username)
        if not user_info:
            raise SmbZfsError(f"User '{username}' is not managed by this tool.")

        self._system.delete_samba_user(username)
        if self._system.user_exists(username):
            self._system.delete_system_user(username)

        if delete_data:
            self._zfs.destroy_dataset(user_info["home_dataset"])

        self._state.delete_item("users", username)
        return f"User '{username}' deleted successfully."

    def create_group(self, groupname, description="", members=None):
        self._check_initialized()
        if not re.match(r"^[a-zA-Z0-9._-]+$", groupname):
            raise SmbZfsError("Group name contains invalid characters.")
        if self._state.get_item("groups", groupname):
            raise SmbZfsError(f"Group '{groupname}' is already managed by this tool.")
        if self._system.group_exists(groupname):
            raise SmbZfsError(f"System group '{groupname}' already exists.")

        self._system.add_system_group(groupname)

        added_members = []
        if members:
            for user in members:
                if self._state.get_item("users", user):
                    self._system.add_user_to_group(user, groupname)
                    added_members.append(user)

        group_config = {
            "description": description or f"{groupname} Group",
            "members": added_members,
            "created": datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._state.set_item("groups", groupname, group_config)
        return f"Group '{groupname}' created successfully."

    def delete_group(self, groupname):
        self._check_initialized()
        if not self._state.get_item("groups", groupname):
            raise SmbZfsError(f"Group '{groupname}' is not managed by this tool.")
        if groupname == "smb_users":
            raise SmbZfsError("Cannot delete the mandatory 'smb_users' group.")

        if self._system.group_exists(groupname):
            self._system.delete_system_group(groupname)

        self._state.delete_item("groups", groupname)
        return f"Group '{groupname}' deleted successfully."

    def create_share(
        self,
        name,
        dataset_path,
        owner,
        group,
        perms="0775",
        comment="",
        valid_users=None,
        read_only=False,
        browseable=True,
    ):
        self._check_initialized()
        if self._state.get_item("shares", name):
            raise SmbZfsError(f"Share '{name}' already exists.")

        pool = self._state.get("zfs_pool")
        full_dataset = f"{pool}/{dataset_path}"

        self._zfs.create_dataset(full_dataset)
        mount_point = self._zfs.get_mountpoint(full_dataset)

        uid = pwd.getpwnam(owner).pw_uid
        gid = grp.getgrnam(group).gr_gid
        os.chown(mount_point, uid, gid)
        os.chmod(mount_point, int(perms, 8))

        share_data = {
            "name": name,
            "comment": comment,
            "path": mount_point,
            "browseable": browseable,
            "read_only": read_only,
            "valid_users": valid_users or f"@{group}",
            "owner": owner,
            "group": group,
        }
        self._config.add_share_to_conf(share_data)
        self._system.test_samba_config()
        self._system.reload_samba()

        state_data = {
            "dataset": full_dataset,
            "path": mount_point,
            "comment": comment,
            "owner": owner,
            "group": group,
            "permissions": perms,
            "valid_users": valid_users or f"@{group}",
            "read_only": read_only,
            "browseable": browseable,
            "created": datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._state.set_item("shares", name, state_data)
        return f"Share '{name}' created successfully."

    def delete_share(self, name, delete_data=False):
        self._check_initialized()
        share_info = self._state.get_item("shares", name)
        if not share_info:
            raise SmbZfsError(f"Share '{name}' is not managed by this tool.")

        self._config.remove_share_from_conf(name)
        self._system.test_samba_config()
        self._system.reload_samba()

        if delete_data:
            self._zfs.destroy_dataset(share_info["dataset"])

        self._state.delete_item("shares", name)
        return f"Share '{name}' deleted successfully."

    def change_password(self, username, new_password):
        self._check_initialized()
        user_info = self._state.get_item("users", username)
        if not user_info:
            raise SmbZfsError(f"User '{username}' is not managed by this tool.")

        if user_info.get("shell_access"):
            self._system.set_system_password(username, new_password)

        self._system.set_samba_password(username, new_password)
        return f"Password changed successfully for user '{username}'."

    def list_items(self, category):
        self._check_initialized()
        if category not in ["users", "groups", "shares"]:
            raise SmbZfsError("Invalid category to list.")
        return self._state.list_items(category)

    def uninstall(self, delete_data=False, delete_users_and_groups=False):
        if not self._state.is_initialized():
            return "System is not installed, nothing to do."

        pool = self._state.get("zfs_pool")
        users = self.list_items("users")
        groups = self.list_items("groups")
        shares = self.list_items("shares")

        if delete_users_and_groups:
            for username in users:
                if self._system.samba_user_exists(username):
                    self._system.delete_samba_user(username)
                if self._system.user_exists(username):
                    self._system.delete_system_user(username)
            for groupname in groups:
                if self._system.group_exists(groupname):
                    self._system.delete_system_group(groupname)
            if self._system.group_exists("smb_users"):
                self._system.delete_system_group("smb_users")

        if delete_data and pool:
            for user_info in users.values():
                self._zfs.destroy_dataset(user_info["home_dataset"])
            for share_info in shares.values():
                if "dataset" in share_info:
                    self._zfs.destroy_dataset(share_info["dataset"])
            self._zfs.destroy_dataset(f"{pool}/homes")

        self._system.stop_services()
        self._system.disable_services()

        for f in [SMB_CONF, AVAHI_SMB_SERVICE, STATE_FILE]:
            if os.path.exists(f):
                os.remove(f)

        self._system.apt_purge(["samba", "samba-common-bin", "avahi-daemon"])
        return "Uninstallation completed successfully."
