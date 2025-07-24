import grp
import os
import pwd
import re
import sys
import json
from contextlib import contextmanager
from datetime import datetime
from functools import wraps

from .config_generator import ConfigGenerator
from .state_manager import StateManager
from .system import System
from .zfs import Zfs
from .const import AVAHI_SMB_SERVICE, SMB_CONF, NAME
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

STATE_FILE=f"/var/lib/{NAME}.state"

def requires_initialization(func):
    """Decorator to ensure the system is initialized before running a method."""

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        self._check_initialized()
        return func(self, *args, **kwargs)

    return wrapper


class SmbZfsManager:
    def __init__(self, state_path=STATE_FILE):
        self._system = System()
        self._zfs = Zfs(self._system)
        self._state = StateManager(state_path)
        self._config = ConfigGenerator()

    @contextmanager
    def _transaction(self):
        """
        A context manager to handle atomic operations. It ensures that if any
        step within the 'with' block fails, all completed steps are rolled back.
        It specifically handles reverting the state file to its pre-transaction
        condition. Other rollbacks (like filesystem or system changes) must be
        added manually to the rollback list.
        """
        rollback_actions = []
        original_state_data = json.loads(json.dumps(self._state.data))  # Deep copy

        try:
            yield rollback_actions
        except Exception as e:
            print(f"Error: An operation failed: {e}", file=sys.stderr)
            print("Attempting to roll back changes...", file=sys.stderr)

            for action in reversed(rollback_actions):
                try:
                    action()
                except Exception as rollback_e:
                    print(
                        f"  - Rollback action failed: {rollback_e}", file=sys.stderr
                    )

            # After attempting rollbacks, restore the state file to its original content
            self._state.data = original_state_data
            self._state.save()
            print("System state has been restored.", file=sys.stderr)

            # Re-raise the original exception so the caller knows the operation failed
            raise e

    def _check_initialized(self):
        """Ensures the system has been initialized."""
        if not self._state.is_initialized():
            raise NotInitializedError()

    def _validate_name(self, name, item_type):
        """
        Validates that a name adheres to the specific rules for its type.
        """
        item_type_lower = item_type.lower()

        if item_type_lower in ["user", "group", "owner"]:
            # POSIX username/group validation: lowercase, start with letter/underscore,
            # can contain letters, numbers, underscore, hyphen. Max 32 chars.
            if not re.match(r"^[a-z_][a-z0-9_-]{0,31}$", name):
                raise InvalidNameError(
                    f"{item_type.capitalize()} name '{name}' is invalid. It must be all lowercase, "
                    "start with a letter or underscore, contain only letters, numbers, "
                    "underscores, or hyphens, and be max 32 characters."
                )
        elif item_type_lower == "share":
            # Samba share name validation: Alphanumeric, period, underscore, hyphen.
            # Max 80 chars.
            if not re.match(r"^[a-zA-Z0-9._-]{1,80}$", name):
                raise InvalidNameError(
                    f"Share name '{name}' is invalid. It can only contain letters, "
                    "numbers, periods, underscores, or hyphens, and be 1-80 characters."
                )
        else:
            if not re.match(r"^[a-zA-Z0-9._-]+$", name):
                raise InvalidNameError(
                    f"{item_type.capitalize()} name '{name}' contains invalid characters."
                )

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

        # Validate that the provided ZFS pool exists.
        available_pools = self._zfs.list_pools()
        if pool not in available_pools:
            raise ItemNotFoundError(f"ZFS pool '{pool}' not found. Available pools", ", ".join(available_pools) if available_pools else "None")


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

    @requires_initialization
    def create_user(self, username, password, allow_shell=False, groups=None, create_home=True):
        self._validate_name(username, "user")
        if self._state.get_item("users", username):
            raise ItemExistsError("user", username)
        if self._system.user_exists(username):
            raise ItemExistsError("system user", username)

        pool = self._state.get("zfs_pool")
        home_dataset_name = f"{pool}/homes/{username}" if create_home else None

        with self._transaction() as rollback:
            user_data = {
                "shell_access": allow_shell,
                "groups": [],
                "created": datetime.utcnow().isoformat(),
            }

            home_mountpoint = None
            if create_home:
                # Action: Create ZFS dataset
                self._zfs.create_dataset(home_dataset_name)
                rollback.append(lambda: self._zfs.destroy_dataset(home_dataset_name))

                home_mountpoint = self._zfs.get_mountpoint(home_dataset_name)

                # Action: Set quota
                default_home_quota = self._state.get("default_home_quota")
                if default_home_quota:
                    self._zfs.set_quota(home_dataset_name, default_home_quota)
                
                user_data["dataset"] = {
                    "name": home_dataset_name,
                    "mount_point": home_mountpoint,
                    "quota": default_home_quota,
                }


            # Action: Add system user
            self._system.add_system_user(
                username,
                home_dir=home_mountpoint if allow_shell else None,
                shell="/bin/bash" if allow_shell else "/usr/sbin/nologin",
            )
            rollback.append(lambda: self._system.delete_system_user(username))

            if create_home:
                # Actions: chown and chmod for home directory
                os.chown(
                    home_mountpoint,
                    pwd.getpwnam(username).pw_uid,
                    pwd.getpwnam(username).pw_gid,
                )
                os.chmod(home_mountpoint, 0o700)

            # Action: Set system password if shell is allowed
            if allow_shell:
                self._system.set_system_password(username, password)

            # Action: Add Samba user
            self._system.add_samba_user(username, password)
            rollback.append(lambda: self._system.delete_samba_user(username))

            # Action: Add user to groups
            self._system.add_user_to_group(username, "smb_users")
            user_groups = []
            if groups:
                for group in groups:
                    if self._state.get_item("groups", group):
                        self._system.add_user_to_group(username, group)
                        user_groups.append(group)
                    else:
                        raise ItemNotFoundError("group", group)
            
            user_data["groups"] = user_groups

            # Action: Update state file (handled by transaction manager)
            self._state.set_item("users", username, user_data)

        return f"User '{username}' created successfully."

    @requires_initialization
    def delete_user(self, username, delete_data=False):
        user_info = self._state.get_item("users", username)
        if not user_info:
            raise ItemNotFoundError("user", username)

        self._system.delete_samba_user(username)
        if self._system.user_exists(username):
            self._system.delete_system_user(username)

        if delete_data and "dataset" in user_info and user_info["dataset"].get("name"):
            self._zfs.destroy_dataset(user_info["dataset"]["name"])

        self._state.delete_item("users", username)
        return f"User '{username}' deleted successfully."

    @requires_initialization
    def create_group(self, groupname, description="", members=None):
        self._validate_name(groupname, "group")
        if self._state.get_item("groups", groupname):
            raise ItemExistsError("group", groupname)
        if self._system.group_exists(groupname):
            raise ItemExistsError("system group", groupname)

        with self._transaction() as rollback:
            # Action: Create system group
            self._system.add_system_group(groupname)
            rollback.append(lambda: self._system.delete_system_group(groupname))

            # Action: Add members to the new group
            added_members = []
            if members:
                for user in members:
                    if not self._state.get_item("users", user):
                        raise ItemNotFoundError("user", user)
                    self._system.add_user_to_group(user, groupname)
                    added_members.append(user)

            # Action: Update state file
            group_config = {
                "description": description or f"{groupname} Group",
                "members": added_members,
                "created": datetime.utcnow().isoformat(),
            }
            self._state.set_item("groups", groupname, group_config)

        return f"Group '{groupname}' created successfully."

    @requires_initialization
    def delete_group(self, groupname):
        if not self._state.get_item("groups", groupname):
            raise ItemNotFoundError("group", groupname)
        if groupname == "smb_users":
            raise ImmutableError("Cannot delete the mandatory 'smb_users' group.")

        if self._system.group_exists(groupname):
            self._system.delete_system_group(groupname)

        self._state.delete_item("groups", groupname)
        return f"Group '{groupname}' deleted successfully."

    @requires_initialization
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
        self._validate_name(name, "share")
        if self._state.get_item("shares", name):
            raise ItemExistsError("share", name)

        if ".." in dataset_path or dataset_path.startswith('/'):
            raise InvalidNameError("Dataset path cannot contain '..' or be an absolute path.")

        if not re.match(r"^[0-7]{3,4}$", perms):
            raise InvalidNameError(f"Permissions '{perms}' are invalid. Must be 3 or 4 octal digits (e.g., 775 or 0775).")

        if not self._system.user_exists(owner):
            raise ItemNotFoundError("user", owner)

        if not self._system.group_exists(group):
            raise ItemNotFoundError("group", group)

        pool = self._state.get("zfs_pool")
        full_dataset = f"{pool}/{dataset_path}"

        with self._transaction() as rollback:
            # Action: Create ZFS dataset
            self._zfs.create_dataset(full_dataset)
            rollback.append(lambda: self._zfs.destroy_dataset(full_dataset))

            if quota:
                self._zfs.set_quota(full_dataset, quota)
            mount_point = self._zfs.get_mountpoint(full_dataset)

            # Action: Set ownership and permissions
            uid = pwd.getpwnam(owner).pw_uid
            gid = grp.getgrnam(group).gr_gid
            os.chown(mount_point, uid, gid)
            os.chmod(mount_point, int(perms, 8))

            if valid_users:
                for item in valid_users.replace(" ", "").split(','):
                    item_name = item.lstrip('@')
                    if '@' in item:
                        if not self._system.group_exists(item_name):
                            raise ItemNotFoundError("group", item_name)
                    else:
                        if not self._system.user_exists(item_name):
                            raise ItemNotFoundError("user", item_name)

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

            # Action: Modify Samba config and reload
            self._config.add_share_to_conf(name, share_data)
            def samba_rollback():
                self._config.remove_share_from_conf(name)
                self._system.test_samba_config()
                self._system.reload_samba()
            rollback.append(samba_rollback)

            self._system.test_samba_config()
            self._system.reload_samba()

            # Action: Update state file
            self._state.set_item("shares", name, share_data)

        return f"Share '{name}' created successfully."

    @requires_initialization
    def delete_share(self, name, delete_data=False):
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

    @requires_initialization
    def modify_group(self, groupname, add_users=None, remove_users=None):
        group_info = self._state.get_item("groups", groupname)
        if not group_info:
            raise ItemNotFoundError("group", groupname)

        current_members = set(group_info.get("members", []))
        if add_users:
            for user in add_users:
                if not self._state.get_item("users", user):
                    raise ItemNotFoundError("user", user)
                self._system.add_user_to_group(user, groupname)
                current_members.add(user)

        if remove_users:
            for user in remove_users:
                if not self._state.get_item("users", user):
                    raise ItemNotFoundError("user", user)
                
                if user in current_members:
                    self._system.remove_user_from_group(user, groupname)
                    current_members.discard(user)

        group_info["members"] = sorted(list(current_members))
        self._state.set_item("groups", groupname, group_info)
        return f"Group '{groupname}' modified successfully."

    @requires_initialization
    def modify_share(self, share_name, **kwargs):
        share_info = self._state.get_item("shares", share_name)
        if not share_info:
            raise ItemNotFoundError("share", share_name)

        samba_config_changed = False
        original_share_info = json.loads(json.dumps(share_info))

        try:
            if 'quota' in kwargs and kwargs['quota'] is not None:
                new_quota = kwargs['quota'] if kwargs['quota'].lower() != 'none' else None
                share_info['dataset']['quota'] = new_quota
                self._zfs.set_quota(share_info["dataset"]["name"], new_quota)
            system_changed = False
            if 'owner' in kwargs and kwargs['owner'] is not None:
                if not self._system.user_exists(kwargs['owner']):
                    raise ItemNotFoundError("user", kwargs['owner'])
                share_info['system']['owner'] = kwargs['owner']
                system_changed = True
            if 'group' in kwargs and kwargs['group'] is not None:
                if not self._system.group_exists(kwargs['group']):
                    raise ItemNotFoundError("group", kwargs['group'])
                share_info['system']['group'] = kwargs['group']
                system_changed = True
            if 'perms' in kwargs and kwargs['perms'] is not None:
                perms = kwargs['perms']
                if not re.match(r"^[0-7]{3,4}$", perms):
                    raise InvalidNameError(f"Permissions '{perms}' are invalid. Must be 3 or 4 octal digits (e.g., 775 or 0775).")
                share_info['system']['permissions'] = perms
                system_changed = True

            if system_changed:
                mount_point = share_info['dataset']['mount_point']
                uid = pwd.getpwnam(share_info['system']['owner']).pw_uid
                gid = grp.getgrnam(share_info['system']['group']).gr_gid
                os.chown(mount_point, uid, gid)
                os.chmod(mount_point, int(share_info['system']['permissions'], 8))
                samba_config_changed = True

            if 'comment' in kwargs and kwargs['comment'] is not None:
                share_info['smb_config']['comment'] = kwargs['comment']
                samba_config_changed = True
            if 'valid_users' in kwargs and kwargs['valid_users'] is not None:
                for item in kwargs['valid_users'].replace(" ", "").split(','):
                    item_name = item.lstrip('@')
                    if '@' in item:
                        if not self._system.group_exists(item_name):
                            raise ItemNotFoundError("group", item_name)
                    else:
                        if not self._system.user_exists(item_name):
                            raise ItemNotFoundError("user", item_name)
                share_info['smb_config']['valid_users'] = kwargs['valid_users']
                samba_config_changed = True
            if 'read_only' in kwargs and kwargs['read_only'] is not None:
                share_info['smb_config']['read_only'] = kwargs['read_only']
                samba_config_changed = True
            if 'browseable' in kwargs and kwargs['browseable'] is not None:
                share_info['smb_config']['browseable'] = kwargs['browseable']
                samba_config_changed = True

            self._state.set_item("shares", share_name, share_info)

            if samba_config_changed:
                self._config.remove_share_from_conf(share_name)
                self._config.add_share_to_conf(share_name, share_info)
                self._system.test_samba_config()
                self._system.reload_samba()

        except Exception:
            # Rollback in-memory and file state on failure
            self._state.set_item("shares", share_name, original_share_info)
            # Re-raise the exception
            raise

        return f"Share '{share_name}' modified successfully."

    @requires_initialization
    def modify_setup(self, **kwargs):
        for key, value in kwargs.items():
            self._state.set(key, value)

        if any(k in kwargs for k in ['server_name', 'workgroup', 'macos_optimized']):
            pool = self._state.get("zfs_pool")
            server_name = self._state.get("server_name")
            workgroup = self._state.get("workgroup")
            macos_optimized = self._state.get("macos_optimized")
            self._config.create_smb_conf(pool, server_name, workgroup, macos_optimized)

            all_shares = self.list_items("shares")
            for share_name, share_info in all_shares.items():
                self._config.add_share_to_conf(share_name, share_info)

            self._system.test_samba_config()
            self._system.reload_samba()

        return "Global setup modified successfully."

    @requires_initialization
    def modify_home(self, username, quota):
        user_info = self._state.get_item("users", username)
        if not user_info:
            raise ItemNotFoundError("user", username)

        home_dataset = user_info["dataset"]["name"]
        new_quota = quota if quota and quota.lower() != 'none' else 'none'
        self._zfs.set_quota(home_dataset, new_quota)
        user_info["dataset"]["quota"] = new_quota
        self._state.set_item("users", username, user_info)
        return f"Quota for user '{username}' has been set to {quota}."

    @requires_initialization
    def change_password(self, username, new_password):
        user_info = self._state.get_item("users", username)
        if not user_info:
            raise ItemNotFoundError("user", username)

        if user_info.get("shell_access"):
            self._system.set_system_password(username, new_password)

        self._system.set_samba_password(username, new_password)
        return f"Password changed successfully for user '{username}'."

    @requires_initialization
    def list_items(self, category):
        if category not in ["users", "groups", "shares"]:
            raise SmbZfsError("Invalid category to list.")

        items = self._state.list_items(category)

        if category == "users":
            for name, data in items.items():
                quota = self._zfs.get_quota(data["dataset"]["name"])
                if data["dataset"]["quota"] != quota:
                    print(f"Warning quota in state for user {name} differs from real quota! state: {data["dataset"]["quota"]}, live:{quota}")
                data["dataset"]["quota"] = quota if quota and quota != 'none' else "Not Set"

        if category == "shares":
            for name, data in items.items():
                quota = self._zfs.get_quota(data["dataset"]["name"])
                if data["dataset"]["quota"] != quota:
                    print(f"Warning quota in state for share {name} differs from real quota! state: {data["dataset"]["quota"]}, live:{quota}")
                data["dataset"]["quota"] = quota if quota and quota != 'none' else "Not Set"

        return items

    def remove(self, delete_data=False, delete_users_and_groups=False):
        if not self._state.is_initialized():
            return "System is not set up, nothing to do."

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
            for share_info in shares.values():
                if "dataset" in share_info:
                    self._zfs.destroy_dataset(share_info["dataset"]["name"])
            for user_info in users.values():
                self._zfs.destroy_dataset(user_info["dataset"]["name"])
            if self._zfs.dataset_exists(f"{pool}/homes"):
                self._zfs.destroy_dataset(f"{pool}/homes")

        self._system.stop_services()
        self._system.disable_services()

        for f in [SMB_CONF, AVAHI_SMB_SERVICE, self._state.path]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError as e:
                    print(f"Warning: could not remove file {f}: {e}", file=sys.stderr)

        return "Removal completed successfully."
