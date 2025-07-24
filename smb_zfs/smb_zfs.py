import grp
import os
import pwd
import re
from datetime import datetime

from . import (
    ConfigGenerator,
    StateManager,
    System,
    Zfs,
    AVAHI_SMB_SERVICE,
    SMB_CONF,
    NAME,
)
from .errors import (
    SmbZfsError,
    NotInitializedError,
    AlreadyInitializedError,
    ItemExistsError,
    ItemNotFoundError,
    InvalidNameError,
    PrerequisiteError,
    ImmutableError,
)


class SmbZfsManager:
    def __init__(self, state_path=f"/var/lib/{NAME}.state"):
        self._system = System()
        self._zfs = Zfs(self._system)
        self._state = StateManager(state_path)
        self._config = ConfigGenerator()

    def _check_initialized(self):
        if not self._state.is_initialized():
            raise NotInitializedError()

    def setup(self, pool, server_name, workgroup, macos_optimized=False, default_home_quota=None):
        if self._state.is_initialized():
            raise AlreadyInitializedError()

        # Check for required Debian packages instead of commands
        required_packages = ["zfsutils-linux", "samba", "avahi-daemon"]
        for pkg in required_packages:
            if not self._system.is_package_installed(pkg):
                raise PrerequisiteError(
                    f"Required package '{pkg}' is not installed. Please install it first."
                )

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
        self._state.set("default_home_quota", default_home_quota)

        self._state.set_item(
            "groups",
            "smb_users",
            {
                "description": "Samba Users Group",
                "members": [],
                "created": datetime.utcnow().isoformat(),
            },
        )
        return "Setup completed successfully."

    def create_user(self, username, password, allow_shell=False, groups=None):
        self._check_initialized()
        if self._state.get_item("users", username):
            raise ItemExistsError("user", username)
        if self._system.user_exists(username):
            raise ItemExistsError("system user", username)

        pool = self._state.get("zfs_pool")
        home_dataset_name = f"{pool}/homes/{username}"

        self._zfs.create_dataset(home_dataset_name)
        home_mountpoint = self._zfs.get_mountpoint(home_dataset_name)

        default_home_quota = self._state.get("default_home_quota")
        if default_home_quota:
            self._zfs.set_quota(home_dataset_name, default_home_quota)

        self._system.add_system_user(
            username,
            home_dir=home_mountpoint if allow_shell else None,
            shell="/bin/bash" if allow_shell else "/usr/sbin/nologin",
        )

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

        user_data = {
            "shell_access": allow_shell,
            "dataset": {
                "name": home_dataset_name,
                "mount_point": home_mountpoint,
                "quota": default_home_quota,
            },
            "groups": user_groups,
            "created": datetime.utcnow().isoformat(),
        }
        self._state.set_item("users", username, user_data)
        return f"User '{username}' created successfully."

    def delete_user(self, username, delete_data=False):
        self._check_initialized()
        user_info = self._state.get_item("users", username)
        if not user_info:
            raise ItemNotFoundError("user", username)

        self._system.delete_samba_user(username)
        if self._system.user_exists(username):
            self._system.delete_system_user(username)

        if delete_data:
            self._zfs.destroy_dataset(user_info["dataset"]["name"])

        self._state.delete_item("users", username)
        return f"User '{username}' deleted successfully."

    def create_group(self, groupname, description="", members=None):
        self._check_initialized()
        if not re.match(r"^[a-zA-Z0-9._-]+$", groupname):
            raise InvalidNameError("Group name contains invalid characters.")
        if self._state.get_item("groups", groupname):
            raise ItemExistsError("group", groupname)
        if self._system.group_exists(groupname):
            raise ItemExistsError("system group", groupname)

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
            "created": datetime.utcnow().isoformat(),
        }
        self._state.set_item("groups", groupname, group_config)
        return f"Group '{groupname}' created successfully."

    def delete_group(self, groupname):
        self._check_initialized()
        if not self._state.get_item("groups", groupname):
            raise ItemNotFoundError("group", groupname)
        if groupname == "smb_users":
            raise ImmutableError("Cannot delete the mandatory 'smb_users' group.")

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
        quota=None,
    ):
        self._check_initialized()
        if self._state.get_item("shares", name):
            raise ItemExistsError("share", name)

        pool = self._state.get("zfs_pool")
        full_dataset = f"{pool}/{dataset_path}"

        self._zfs.create_dataset(full_dataset)
        if quota:
            self._zfs.set_quota(full_dataset, quota)
        mount_point = self._zfs.get_mountpoint(full_dataset)

        uid = pwd.getpwnam(owner).pw_uid
        gid = grp.getgrnam(group).gr_gid
        os.chown(mount_point, uid, gid)
        os.chmod(mount_point, int(perms, 8))

        share_data = {
            "dataset": {
                "name": full_dataset,
                "mount_point": mount_point,
                "quota": quota,
            },
            "smb_config": {
                "comment": comment,
                "browseable": browseable,
                "read_only": read_only,
                "valid_users": valid_users or f"@{group}",
            },
            "system": {
                "owner": owner,
                "group": group,
                "permissions": perms,
            },
            "created": datetime.utcnow().isoformat(),
        }

        self._config.add_share_to_conf(name, share_data)
        self._system.test_samba_config()
        self._system.reload_samba()

        self._state.set_item("shares", name, share_data)
        return f"Share '{name}' created successfully."

    def delete_share(self, name, delete_data=False):
        self._check_initialized()
        share_info = self._state.get_item("shares", name)
        if not share_info:
            raise ItemNotFoundError("share", name)

        self._config.remove_share_from_conf(name)
        self._system.test_samba_config()
        self._system.reload_samba()

        if delete_data:
            self._zfs.destroy_dataset(share_info["dataset"]["name"])

        self._state.delete_item("shares", name)
        return f"Share '{name}' deleted successfully."

    def modify_group(self, groupname, add_users=None, remove_users=None):
        self._check_initialized()
        group_info = self._state.get_item("groups", groupname)
        if not group_info:
            raise ItemNotFoundError("group", groupname)

        current_members = set(group_info.get("members", []))
        if add_users:
            for user in add_users:
                if not self._state.get_item("users", user):
                    print(f"Warning: User '{user}' not managed by this tool. Skipping.")
                    continue
                self._system.add_user_to_group(user, groupname)
                current_members.add(user)

        if remove_users:
            for user in remove_users:
                self._system.remove_user_from_group(user, groupname)
                current_members.discard(user)

        group_info["members"] = sorted(list(current_members))
        self._state.set_item("groups", groupname, group_info)
        return f"Group '{groupname}' modified successfully."

    def modify_share(self, share_name, **kwargs):
        self._check_initialized()
        share_info = self._state.get_item("shares", share_name)
        if not share_info:
            raise ItemNotFoundError("share", share_name)

        # Flag to track if smb.conf needs a reload
        samba_config_changed = False

        # Handle quota change
        if 'quota' in kwargs and kwargs['quota'] is not None:
            new_quota = kwargs['quota'] if kwargs['quota'].lower() != 'none' else None
            share_info['dataset']['quota'] = new_quota
            self._zfs.set_quota(share_info["dataset"]["name"], new_quota)

        # Handle system-level changes (owner, group, perms)
        system_changed = False
        if 'owner' in kwargs and kwargs['owner'] is not None:
            share_info['system']['owner'] = kwargs['owner']
            system_changed = True
        if 'group' in kwargs and kwargs['group'] is not None:
            share_info['system']['group'] = kwargs['group']
            system_changed = True
        if 'perms' in kwargs and kwargs['perms'] is not None:
            share_info['system']['permissions'] = kwargs['perms']
            system_changed = True

        if system_changed:
            mount_point = share_info['dataset']['mount_point']
            uid = pwd.getpwnam(share_info['system']['owner']).pw_uid
            gid = grp.getgrnam(share_info['system']['group']).gr_gid
            os.chown(mount_point, uid, gid)
            os.chmod(mount_point, int(share_info['system']['permissions'], 8))
            samba_config_changed = True # force user/group is in smb.conf

        # Handle Samba-specific config changes
        if 'comment' in kwargs and kwargs['comment'] is not None:
            share_info['smb_config']['comment'] = kwargs['comment']
            samba_config_changed = True
        if 'valid_users' in kwargs and kwargs['valid_users'] is not None:
            share_info['smb_config']['valid_users'] = kwargs['valid_users']
            samba_config_changed = True
        if 'readonly' in kwargs and kwargs['readonly'] is not None:
            share_info['smb_config']['read_only'] = kwargs['readonly']
            samba_config_changed = True
        if 'no_browse' in kwargs and kwargs['no_browse'] is not None:
            share_info['smb_config']['browseable'] = not kwargs['no_browse']
            samba_config_changed = True

        # Save the updated state
        self._state.set_item("shares", share_name, share_info)

        # If any samba-related config changed, regenerate the conf entry and reload
        if samba_config_changed:
            self._config.remove_share_from_conf(share_name)
            self._config.add_share_to_conf(share_name, share_info)
            self._system.test_samba_config()
            self._system.reload_samba()

        return f"Share '{share_name}' modified successfully."

    def modify_setup(self, **kwargs):
        self._check_initialized()

        # Update state with any new values.
        for key, value in kwargs.items():
            if value is None and key == 'default_home_quota':
                self._state.set(key, None)
            elif value is not None:
                self._state.set(key, value)


        # Regenerate smb.conf with new global settings if needed
        if any(k in kwargs for k in ['server_name', 'workgroup', 'macos_optimized']):
            pool = self._state.get("zfs_pool")
            server_name = self._state.get("server_name")
            workgroup = self._state.get("workgroup")
            macos_optimized = self._state.get("macos_optimized")
            self._config.create_smb_conf(pool, server_name, workgroup, macos_optimized)

            # Re-add all existing shares to the new config
            all_shares = self.list_items("shares")
            for share_name, share_info in all_shares.items():
                self._config.add_share_to_conf(share_name, share_info)

            self._system.test_samba_config()
            self._system.reload_samba()

        return "Global setup modified successfully."

    def modify_home(self, username, quota):
        self._check_initialized()
        user_info = self._state.get_item("users", username)
        if not user_info:
            raise ItemNotFoundError("user", username)

        home_dataset = user_info["dataset"]["name"]
        self._zfs.set_quota(home_dataset, quota)
        user_info["dataset"]["quota"] = quota
        self._state.set_item("users", username, user_info)
        return f"Quota for user '{username}' has been set to {quota}."

    def change_password(self, username, new_password):
        self._check_initialized()
        user_info = self._state.get_item("users", username)
        if not user_info:
            raise ItemNotFoundError("user", username)

        if user_info.get("shell_access"):
            self._system.set_system_password(username, new_password)

        self._system.set_samba_password(username, new_password)
        return f"Password changed successfully for user '{username}'."

    def list_items(self, category):
        self._check_initialized()
        if category not in ["users", "groups", "shares"]:
            raise SmbZfsError("Invalid category to list.")

        items = self._state.list_items(category)

        # Update with live data
        if category == "users":
            for name, data in items.items():
                quota = self._zfs.get_quota(data["dataset"]["name"])
                data["dataset"]["quota"] = quota if quota and quota != 'none' else "Not Set"

        if category == "shares":
            for name, data in items.items():
                quota = self._zfs.get_quota(data["dataset"]["name"])
                data["dataset"]["quota"] = quota if quota and quota != 'none' else "Not Set"

        return items

    def remove(self, delete_data=False, delete_users_and_groups=False):
        if not self._state.is_initialized():
            return "System is not set up, nothing to do."

        pool = self._state.get("zfs_pool")
        users = self.list_items("users")
        groups = self.list_items("groups")

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
                self._zfs.destroy_dataset(user_info["dataset"]["name"])
            all_shares = self.list_items("shares")
            for share_info in all_shares.values():
                if "dataset" in share_info:
                    self._zfs.destroy_dataset(share_info["dataset"]["name"])
            self._zfs.destroy_dataset(f"{pool}/homes")

        self._system.stop_services()
        self._system.disable_services()

        for f in [SMB_CONF, AVAHI_SMB_SERVICE, self._state.path]:
            if os.path.exists(f):
                os.remove(f)

        return "Removal completed successfully."
