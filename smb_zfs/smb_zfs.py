import grp
import os
import pwd
import re
import logging
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from typing import List, Dict, Any, Optional, Generator, Callable

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
    StateItemNotFoundError,
    InvalidNameError,
    InvalidInputError,
    PrerequisiteError,
    MissingInput,
)

# --- Constants and Logger Setup ---
STATE_FILE = f"/var/lib/{NAME}.state"
logger = logging.getLogger(__name__)


# --- Decorators ---
def requires_initialization(func: Callable) -> Callable:
    """Decorator to ensure the system is initialized before running a method."""
    @wraps(func)
    def wrapper(self: 'SmbZfsManager', *args: Any, **kwargs: Any) -> Any:
        self._check_initialized()
        return func(self, *args, **kwargs)
    return wrapper


# --- Main Class ---
class SmbZfsManager:
    """Manages Samba, ZFS, and system configurations for a NAS environment."""

    def __init__(self, state_path: str = STATE_FILE) -> None:
        """Initializes the manager with its core components."""
        self._system = System()
        self._zfs = Zfs(self._system)
        self._state = StateManager(state_path)
        self._config = ConfigGenerator()
        logger.debug(
            "SmbZfsManager initialized with state file: %s", state_path)

    @contextmanager
    def _transaction(self) -> Generator[List[Callable[[], None]], None, None]:
        """A context manager to handle atomic operations with state rollback."""
        rollback_actions: List[Callable[[], None]] = []
        original_state_data = self._state.get_data_copy()
        logger.debug("Transaction started. Original state backed up.")
        try:
            yield rollback_actions
        except Exception as e:
            # Error logging is handled by the calling CLI, but we log the rollback attempt.
            logger.warning("Operation failed: %s. Rolling back changes.", e)
            for action in reversed(rollback_actions):
                try:
                    action()
                    logger.info("Rollback action executed successfully.")
                except Exception as rollback_e:
                    logger.error("Rollback action failed: %s",
                                 rollback_e, exc_info=True)
            self._state.data = original_state_data
            self._state.save()
            logger.info("System state has been restored from backup.")
            raise

    def _check_initialized(self) -> None:
        """Ensures the system has been initialized."""
        if not self._state.is_initialized():
            raise NotInitializedError()
        logger.debug("Initialization check passed.")

    def _validate_name(self, name: str, item_type: str) -> None:
        """Validates that a name adheres to the specific rules for its type."""
        logger.debug("Validating name '%s' for type '%s'.", name, item_type)
        item_type_lower = item_type.lower()
        if item_type_lower in ["user", "group", "owner"]:
            if not re.match(r"^[a-z_][a-z0-9_-]{0,31}$", name):
                raise InvalidNameError(
                    f"{item_type.capitalize()} name '{name}' is invalid. It must be all lowercase, "
                    "start with a letter or underscore, contain only letters, numbers, "
                    "underscores, or hyphens, and be max 32 characters."
                )
        elif item_type_lower == "share":
            if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-:]{0,79}$", name) or \
                    any(component == "" for component in re.split(r"[._\-:]", name)):
                raise InvalidNameError(
                    f"{item_type.capitalize()} name '{name}' is invalid. It must start with a letter or number, "
                    "contain only alphanumeric characters, underscores (_), hyphens (-), colons (:), or periods (.), "
                    "have no empty components, and be 1-80 characters long."
                )
        elif item_type_lower in ['server_name', 'workgroup']:
            if not re.match(r"^(?!-)[A-Za-z0-9-]{1,15}(?<!-)$", name):
                raise InvalidNameError(
                    f"{item_type.capitalize()} name '{name}' is invalid. It must be 1-15 characters long, "
                    "contain only letters, numbers, or hyphens, and must not start or end with a hyphen."
                )
        else:
            if not re.match(r"^[a-zA-Z0-9._-]+$", name):
                raise InvalidNameError(
                    f"{item_type.capitalize()} name '{name}' contains invalid characters."
                )
        logger.debug("Name '%s' is valid.", name)


    def _validate_quota(self, quota: str) -> None:
        logger.debug("Validating quota '%s'", quota)
        if not re.match(r'^none$|^\d+\.?\d*[kmgtpez]?$', quota.lower()):
            raise InvalidInputError(
                f"Quota musst be either 'none' or a numeric value followed by a letter, e.g.: 512M, 120G, 1.5T"
            )
        logger.debug("Quota '%s' is valid.", quota)


    def setup(self, primary_pool: str, secondary_pools: Optional[List[str]], server_name: str, workgroup: str, macos_optimized: bool = False, default_home_quota: Optional[str] = None) -> Dict[str, Any]:
        """Initializes the system, configures Samba, and sets up ZFS datasets."""
        logger.info("Starting system setup...")
        if self._state.is_initialized():
            raise AlreadyInitializedError()

        self._validate_name(server_name, 'server_name')
        self._validate_name(workgroup, 'workgroup')

        secondary_pools = secondary_pools or []

        required_packages = ["zfsutils-linux", "samba", "avahi-daemon"]
        for pkg in required_packages:
            if not self._system.is_package_installed(pkg):
                raise PrerequisiteError(
                    f"Required package '{pkg}' is not installed. Please install it first."
                )
            logger.debug("Package '%s' is installed.", pkg)

        available_pools = self._zfs.list_pools()
        if primary_pool not in available_pools:
            raise StateItemNotFoundError(f"ZFS pool '{primary_pool}' not found. Available pools", ", ".join(
                available_pools) if available_pools else "None")
        for pool in secondary_pools:
            if pool not in available_pools:
                raise StateItemNotFoundError(f"ZFS secondary pool '{pool}' not found. Available pools", ", ".join(
                    available_pools) if available_pools else "None")

        logger.info(
            "Creating primary homes dataset in pool '%s'.", primary_pool)
        self._zfs.create_dataset(f"{primary_pool}/homes")
        homes_mountpoint = self._zfs.get_mountpoint(f"{primary_pool}/homes")
        os.chmod(homes_mountpoint, 0o755)

        if not self._system.group_exists("smb_users"):
            logger.info("Creating 'smb_users' system group.")
            self._system.add_system_group("smb_users")

        logger.info("Generating Samba and Avahi configurations.")
        self._config.create_smb_conf(
            primary_pool, server_name, workgroup, macos_optimized)
        self._config.create_avahi_conf()

        logger.info("Testing and applying new configurations.")
        self._system.test_samba_config()
        self._system.enable_services()
        self._system.restart_services()

        if default_home_quota:
            self._validate_quota(default_home_quota)

        logger.info("Saving initial state configuration.")
        self._state.set("initialized", True)
        self._state.set("primary_pool", primary_pool)
        self._state.set("secondary_pools", secondary_pools)
        self._state.set("server_name", server_name)
        self._state.set("workgroup", workgroup)
        self._state.set("macos_optimized", macos_optimized)
        self._state.set("default_home_quota", default_home_quota)
        self._state.set_item("groups", "smb_users", {"description": "Samba Users Group", "members": [
        ], "created": datetime.utcnow().isoformat()})

        logger.info("Setup completed successfully.")
        return {"msg": "Setup completed successfully.", "state": self._state.get_data_copy()}

    @requires_initialization
    def create_user(self, username: str, password: str, allow_shell: bool = False, groups: Optional[List[str]] = None, create_home: bool = True) -> Dict[str, Any]:
        """Creates a new system and Samba user with an optional ZFS home directory."""
        logger.info("Attempting to create user '%s'.", username)
        self._validate_name(username, "user")
        if self._state.get_item("users", username):
            raise ItemExistsError("user", username)
        if self._system.user_exists(username):
            raise ItemExistsError("system user", username)

        primary_pool = self._state.get("primary_pool")
        home_dataset_name = f"{primary_pool}/homes/{username}" if create_home else None

        with self._transaction() as rollback:
            user_data: Dict[str, Any] = {"shell_access": allow_shell, "groups": [
            ], "created": datetime.utcnow().isoformat()}
            home_mountpoint = None

            if create_home and home_dataset_name:
                logger.info("Creating home dataset '%s'.", home_dataset_name)
                self._zfs.create_dataset(home_dataset_name)
                rollback.append(
                    lambda: self._zfs.destroy_dataset(home_dataset_name))
                home_mountpoint = self._zfs.get_mountpoint(home_dataset_name)

                default_home_quota = self._state.get("default_home_quota")
                if default_home_quota:
                    self._zfs.set_quota(home_dataset_name, default_home_quota)

                user_data["dataset"] = {
                    "name": home_dataset_name, "mount_point": home_mountpoint, "quota": default_home_quota, "pool": primary_pool}

            logger.info("Adding system user '%s'.", username)
            self._system.add_system_user(username, home_dir=home_mountpoint if allow_shell else None, shell=(
                "/bin/bash" if allow_shell else "/usr/sbin/nologin"))
            rollback.append(lambda: self._system.delete_system_user(username))

            if create_home and home_mountpoint:
                uid = pwd.getpwnam(username).pw_uid
                gid = pwd.getpwnam(username).pw_gid
                os.chown(home_mountpoint, uid, gid)
                os.chmod(home_mountpoint, 0o700)
                logger.debug(
                    "Set permissions on home directory for '%s'.", username)

            if allow_shell:
                self._system.set_system_password(username, password)

            logger.info("Adding Samba user '%s'.", username)
            self._system.add_samba_user(username, password)
            rollback.append(lambda: self._system.delete_samba_user(username))

            self._system.add_user_to_group(username, "smb_users")
            user_groups = []
            if groups:
                for group in groups:
                    if self._state.get_item("groups", group):
                        self._system.add_user_to_group(username, group)
                        user_groups.append(group)
                    else:
                        logger.warning(
                            "Group '%s' not found in state, skipping for user '%s'.", group, username)
                        raise StateItemNotFoundError("group", group)
            user_data["groups"] = user_groups

            self._state.set_item("users", username, user_data)

        logger.info("User '%s' created successfully.", username)
        return {"msg": f"User '{username}' created successfully.", "state": self._state.get_data_copy()}

    @requires_initialization
    def delete_user(self, username: str, delete_data: bool = False) -> Dict[str, Any]:
        """Deletes a user from the system, Samba, and optionally their data."""
        logger.info("Attempting to delete user '%s'.", username)
        user_info = self._state.get_item("users", username)
        if not user_info:
            raise StateItemNotFoundError("user", username)

        logger.info("Deleting Samba user '%s'.", username)
        self._system.delete_samba_user(username)
        if self._system.user_exists(username):
            logger.info("Deleting system user '%s'.", username)
            self._system.delete_system_user(username)

        if delete_data and "dataset" in user_info and user_info["dataset"].get("name"):
            dataset_name = user_info["dataset"]["name"]
            logger.warning(
                "Deleting user data and dataset '%s'.", dataset_name)
            self._zfs.destroy_dataset(dataset_name)

        self._state.delete_item("users", username)
        logger.info("User '%s' deleted successfully.", username)
        return {"msg": f"User '{username}' deleted successfully.", "state": self._state.get_data_copy()}

    @requires_initialization
    def create_group(self, groupname: str, description: str = "", members: Optional[List[str]] = None) -> Dict[str, Any]:
        """Creates a new system group and registers it in the state."""
        logger.info("Attempting to create group '%s'.", groupname)
        self._validate_name(groupname, "group")
        if self._state.get_item("groups", groupname):
            raise ItemExistsError("group", groupname)
        if self._system.group_exists(groupname):
            raise ItemExistsError("system group", groupname)

        with self._transaction() as rollback:
            logger.info("Adding system group '%s'.", groupname)
            self._system.add_system_group(groupname)
            rollback.append(
                lambda: self._system.delete_system_group(groupname))

            added_members = []
            if members:
                for user in members:
                    if not self._state.get_item("users", user):
                        raise StateItemNotFoundError("user", user)
                    self._system.add_user_to_group(user, groupname)
                    added_members.append(user)

            group_config = {"description": description or f"{groupname} Group",
                            "members": added_members, "created": datetime.utcnow().isoformat()}
            self._state.set_item("groups", groupname, group_config)

        logger.info("Group '%s' created successfully.", groupname)
        return {"msg": f"Group '{groupname}' created successfully.", "state": self._state.get_data_copy()}

    @requires_initialization
    def delete_group(self, groupname: str) -> Dict[str, Any]:
        """Deletes a group from the system and state."""
        logger.info("Attempting to delete group '%s'.", groupname)
        if not self._state.get_item("groups", groupname):
            raise StateItemNotFoundError("group", groupname)
        if groupname == "smb_users":
            raise SmbZfsError("Cannot delete the mandatory 'smb_users' group.")

        if self._system.group_exists(groupname):
            logger.info("Deleting system group '%s'.", groupname)
            self._system.delete_system_group(groupname)

        self._state.delete_item("groups", groupname)
        logger.info("Group '%s' deleted successfully.", groupname)
        return {"msg": f"Group '{groupname}' deleted successfully.", "state": self._state.get_data_copy()}

    @requires_initialization
    def create_share(self, name: str, dataset_path: str, owner: str, group: str, perms: str = "0775", comment: str = "", valid_users: Optional[str] = None, read_only: bool = False, browseable: bool = True, quota: Optional[str] = None, pool: Optional[str] = None) -> Dict[str, Any]:
        """Creates a ZFS dataset and configures it as a Samba share."""
        logger.info(
            "Attempting to create share '%s' on dataset path '%s'.", name, dataset_path)
        self._validate_name(name, "share")
        if self._state.get_item("shares", name):
            raise ItemExistsError("share", name)
        if ".." in dataset_path or dataset_path.startswith('/'):
            raise InvalidNameError(
                "Dataset path cannot contain '..' or be an absolute path.")
        if not re.match(r"^[0-7]{3,4}$", perms):
            raise InvalidNameError(
                f"Permissions '{perms}' are invalid. Must be 3 or 4 octal digits (e.g., 775 or 0775).")
        if not self._system.user_exists(owner):
            raise StateItemNotFoundError("user", owner)
        if not self._system.group_exists(group):
            raise StateItemNotFoundError("group", group)

        primary_pool = self._state.get("primary_pool")
        secondary_pools = self._state.get("secondary_pools", [])
        managed_pools = [primary_pool] + secondary_pools
        target_pool = pool or primary_pool
        if target_pool not in managed_pools:
            raise SmbZfsError(
                f"Pool '{target_pool}' is not a valid pool. Managed pools are: {', '.join(managed_pools)}")

        full_dataset = f"{target_pool}/{dataset_path}"
        with self._transaction() as rollback:
            logger.info("Creating dataset '%s'.", full_dataset)
            self._zfs.create_dataset(full_dataset)
            rollback.append(lambda: self._zfs.destroy_dataset(full_dataset))

            if quota:
                self._validate_quota(quota)
                self._zfs.set_quota(full_dataset, quota)

            mount_point = self._zfs.get_mountpoint(full_dataset)
            uid = pwd.getpwnam(owner).pw_uid
            gid = grp.getgrnam(group).gr_gid
            os.chown(mount_point, uid, gid)
            os.chmod(mount_point, int(perms, 8))
            logger.debug("Set permissions on mount point '%s'.", mount_point)

            if valid_users:
                for item in valid_users.replace(" ", "").split(','):
                    item_name = item.lstrip('@')
                    if '@' in item:
                        if not self._system.group_exists(item_name):
                            raise StateItemNotFoundError("group", item_name)
                    else:
                        if not self._system.user_exists(item_name):
                            raise StateItemNotFoundError("user", item_name)

            share_data = {
                "dataset": {"name": full_dataset, "mount_point": mount_point, "quota": quota, "pool": target_pool},
                "smb_config": {"comment": comment, "browseable": browseable, "read_only": read_only, "valid_users": valid_users or f"@{group}"},
                "system": {"owner": owner, "group": group, "permissions": perms},
                "created": datetime.utcnow().isoformat(),
            }

            logger.info("Adding share '%s' to Samba configuration.", name)
            self._config.add_share_to_conf(name, share_data)

            def samba_rollback():
                self._config.remove_share_from_conf(name)
                self._system.test_samba_config()
                self._system.reload_samba()
            rollback.append(samba_rollback)

            self._system.test_samba_config()
            self._system.reload_samba()
            self._state.set_item("shares", name, share_data)

        logger.info("Share '%s' created successfully.", name)
        return {"msg": f"Share '{name}' created successfully.", "state": self._state.get_data_copy()}

    @requires_initialization
    def delete_share(self, name: str, delete_data: bool = False) -> Dict[str, Any]:
        """Deletes a Samba share and optionally its underlying ZFS dataset."""
        logger.info("Attempting to delete share '%s'.", name)
        share_info = self._state.get_item("shares", name)
        if not share_info:
            raise StateItemNotFoundError("share", name)

        logger.info("Removing share '%s' from Samba configuration.", name)
        self._config.remove_share_from_conf(name)
        self._system.test_samba_config()
        self._system.reload_samba()

        if delete_data:
            dataset_name = share_info["dataset"]["name"]
            logger.warning(
                "Deleting share data and dataset '%s'.", dataset_name)
            self._zfs.destroy_dataset(dataset_name)

        self._state.delete_item("shares", name)
        logger.info("Share '%s' deleted successfully.", name)
        return {"msg": f"Share '{name}' deleted successfully.", "state": self._state.get_data_copy()}

    @requires_initialization
    def modify_group(self, groupname: str, add_users: Optional[List[str]] = None, remove_users: Optional[List[str]] = None) -> Dict[str, Any]:
        """Adds or removes users from a group."""
        logger.info("Attempting to modify group '%s'.", groupname)
        group_info = self._state.get_item("groups", groupname)
        if not group_info:
            raise StateItemNotFoundError("group", groupname)
        if not add_users and not remove_users:
            raise MissingInput('Found no users to add or remove!')

        current_members = set(group_info.get("members", []))
        if add_users:
            for user in add_users:
                if not self._state.get_item("users", user):
                    raise StateItemNotFoundError("user", user)
                self._system.add_user_to_group(user, groupname)
                current_members.add(user)
                logger.debug("Added user '%s' to group '%s'.", user, groupname)
        if remove_users:
            for user in remove_users:
                if not self._state.get_item("users", user):
                    raise StateItemNotFoundError("user", user)
                if user in current_members:
                    self._system.remove_user_from_group(user, groupname)
                    current_members.discard(user)
                    logger.debug(
                        "Removed user '%s' from group '%s'.", user, groupname)
                else:
                    logger.warning(
                        "User '%s' is not a member of group '%s', skipping removal.", user, groupname)

        group_info["members"] = sorted(list(current_members))
        self._state.set_item("groups", groupname, group_info)
        logger.info("Group '%s' modified successfully.", groupname)
        return {"msg": f"Group '{groupname}' modified successfully.", "state": self._state.get_data_copy()}

    @requires_initialization
    def modify_share(self, share_name: str, name: Optional[str] = None, pool: Optional[str] = None, quota: Optional[str] = None, owner: Optional[str] = None, group: Optional[str] = None, permissions: Optional[str] = None, comment: Optional[str] = None, valid_users: Optional[str] = None, read_only: Optional[bool] = None, browseable: Optional[bool] = None) -> Dict[str, Any]:
        """Modifies various properties of an existing share."""
        logger.info("Attempting to modify share '%s'.", share_name)
        original_state = self._state.get_data_copy()
        original_share_name = share_name
        share_info = self._state.get_item("shares", share_name)
        if not share_info:
            raise StateItemNotFoundError("share", share_name)

        samba_config_changed = False
        try:
            if pool is not None and pool != share_info['dataset']['pool']:
                logger.info("Moving share '%s' from pool '%s' to '%s'.",
                            share_name, share_info['dataset']['pool'], pool)
                primary_pool = self._state.get("primary_pool")
                secondary_pools = self._state.get("secondary_pools", [])
                if pool not in ([primary_pool] + secondary_pools):
                    raise SmbZfsError(
                        f"Target pool '{pool}' is not a valid managed pool.")

                old_dataset_name = share_info['dataset']['name']
                dataset_path_in_pool = '/'.join(
                    old_dataset_name.split('/')[1:])
                new_dataset_name = f"{pool}/{dataset_path_in_pool}"
                self._zfs.move_dataset(old_dataset_name, pool)
                share_info['dataset']['pool'] = pool
                share_info['dataset']['name'] = new_dataset_name
                share_info['dataset']['mount_point'] = self._zfs.get_mountpoint(
                    new_dataset_name)
                samba_config_changed = True

            if name is not None:
                logger.info("Renaming share '%s' to '%s'.", share_name, name)
                new_share_name = name.lower()
                # Validate new share name and ensure no collision
                self._validate_name(new_share_name, "share")
                if new_share_name != original_share_name and self._state.get_item("shares", new_share_name):
                    raise ItemExistsError("share", new_share_name)

                current_dataset_path = share_info['dataset']['name']
                parent_dataset_path = '/'.join(current_dataset_path.split('/')[:-1])
                new_dataset_name = f"{parent_dataset_path}/{new_share_name}"
                self._zfs.rename_dataset(current_dataset_path, new_dataset_name)
                share_info['dataset']['name'] = new_dataset_name
                share_info['dataset']['mount_point'] = self._zfs.get_mountpoint(new_dataset_name)

                self._state.set_item("shares", new_share_name, share_info)
                share_info = self._state.get_item("shares", new_share_name)  # Re-fetch info under new name
                self._state.delete_item("shares", original_share_name)
                share_name = new_share_name  # Update for subsequent operations in this method
                samba_config_changed = True

            if quota is not None:
                self._validate_quota(quota)
                new_quota = 'none' if str(quota).lower() == 'none' else quota
                logger.info("Setting quota for share '%s' to '%s'.",
                            share_name, new_quota)
                share_info['dataset']['quota'] = new_quota
                self._zfs.set_quota(share_info["dataset"]["name"], new_quota)

            system_changed = False
            if owner is not None:
                if not self._system.user_exists(owner):
                    raise StateItemNotFoundError("user", owner)
                logger.info("Changing owner of share '%s' to '%s'.",
                            share_name, owner)
                share_info['system']['owner'] = owner
                system_changed = True
            if group is not None:
                if not self._system.group_exists(group):
                    raise StateItemNotFoundError("group", group)
                logger.info("Changing group of share '%s' to '%s'.",
                            share_name, group)
                share_info['system']['group'] = group
                system_changed = True
            if permissions is not None:
                if not re.match(r"^[0-7]{3,4}$", permissions):
                    raise InvalidNameError(
                        f"Permissions '{permissions}' are invalid.")
                logger.info(
                    "Changing permissions of share '%s' to '%s'.", share_name, permissions)
                share_info['system']['permissions'] = permissions
                system_changed = True

            if system_changed:
                logger.debug(
                    "Applying system permission changes for share '%s'.", share_name)
                mount_point = share_info['dataset']['mount_point']
                uid = pwd.getpwnam(share_info['system']['owner']).pw_uid
                gid = grp.getgrnam(share_info['system']['group']).gr_gid
                os.chown(mount_point, uid, gid)
                os.chmod(mount_point, int(
                    share_info['system']['permissions'], 8))

            if comment is not None:
                share_info['smb_config']['comment'] = comment
                samba_config_changed = True
            if valid_users is not None:
                for item in valid_users.replace(" ", "").split(','):
                    item_name = item.lstrip('@')
                    if '@' in item and not self._system.group_exists(item_name):
                        raise StateItemNotFoundError("group", item_name)
                    elif '@' not in item and not self._system.user_exists(item_name):
                        raise StateItemNotFoundError("user", item_name)
                share_info['smb_config']['valid_users'] = valid_users
                samba_config_changed = True
            if read_only is not None:
                share_info['smb_config']['read_only'] = read_only
                samba_config_changed = True
            if browseable is not None:
                share_info['smb_config']['browseable'] = browseable
                samba_config_changed = True

            self._state.set_item("shares", share_name, share_info)

            if samba_config_changed:
                logger.info(
                    "Updating Samba configuration for share '%s'.", share_name)
                self._config.remove_share_from_conf(original_share_name)
                self._config.add_share_to_conf(share_name, share_info)
                self._system.test_samba_config()
                self._system.reload_samba()
        except Exception as e:
            self._state.data = original_state
            self._state.save()
            logger.error(
                "Error during share modification: %s. State restored, but filesystem changes might need manual rollback.", e)
            raise

        logger.info("Share '%s' modified successfully.", original_share_name)
        return {"msg": f"Share '{original_share_name}' modified successfully.", "state": self._state.get_data_copy()}

    @requires_initialization
    def modify_setup(self, primary_pool: Optional[str] = None, add_secondary_pools: Optional[List[str]] = None, remove_secondary_pools: Optional[List[str]] = None, server_name: Optional[str] = None, workgroup: Optional[str] = None, macos_optimized: Optional[bool] = None, default_home_quota: Optional[str] = None) -> Dict[str, Any]:
        """Modifies global setup parameters."""
        logger.info("Attempting to modify global setup.")
        original_state = self._state.get_data_copy()
        config_needs_update = False
        add_pools = add_secondary_pools or []
        remove_pools = remove_secondary_pools or []

        if default_home_quota:
            self._validate_quota(default_home_quota)
        if server_name:
            self._validate_name(server_name, 'server_name')
        if workgroup:
            self._validate_name(workgroup, 'workgroup')

        try:
            if primary_pool is not None:
                old_primary_pool = self._state.get('primary_pool')
                if primary_pool != old_primary_pool:
                    logger.info("Changing primary pool from '%s' to '%s'.",
                                old_primary_pool, primary_pool)
                    if primary_pool not in self._zfs.list_pools():
                        raise StateItemNotFoundError("ZFS pool", primary_pool)

                    all_users = self._state.list_items("users")
                    for username, user_info in all_users.items():
                        logger.debug(
                            "Moving user '%s' home dataset to new primary pool.", username)
                        self._zfs.move_dataset(
                            user_info['dataset']['name'], primary_pool)
                        user_info['dataset']['name'] = user_info['dataset']['name'].replace(
                            old_primary_pool, primary_pool, 1)
                        user_info['dataset']['mount_point'] = self._zfs.get_mountpoint(
                            user_info['dataset']['name'])
                        user_info['dataset']['pool'] = primary_pool
                        self._state.set_item("users", username, user_info)

                    all_shares = self._state.list_items("shares")
                    for share_name, share_info in all_shares.items():
                        if share_info['dataset']['pool'] == old_primary_pool:
                            logger.debug(
                                "Moving share '%s' dataset to new primary pool.", share_name)
                            old_dataset_name = share_info['dataset']['name']
                            dataset_path_in_pool = '/'.join(
                                old_dataset_name.split('/')[1:])
                            self._zfs.move_dataset(
                                old_dataset_name, primary_pool)
                            new_dataset_name = f"{primary_pool}/{dataset_path_in_pool}"
                            share_info['dataset']['pool'] = primary_pool
                            share_info['dataset']['name'] = new_dataset_name
                            share_info['dataset']['mount_point'] = self._zfs.get_mountpoint(
                                new_dataset_name)
                            self._state.set_item(
                                "shares", share_name, share_info)

                    self._state.set('primary_pool', primary_pool)
                    config_needs_update = True

            if add_pools:
                current_pools = set(self._state.get('secondary_pools', []))
                for pool in add_pools:
                    if pool not in self._zfs.list_pools():
                        raise StateItemNotFoundError("ZFS pool", pool)
                    current_pools.add(pool)
                self._state.set('secondary_pools', sorted(list(current_pools)))
                logger.info("Added secondary pools: %s", ", ".join(add_pools))

            if remove_pools:
                pools_to_remove = set(remove_pools)
                all_shares = self._state.list_items("shares")
                for share_name, share_info in all_shares.items():
                    if share_info['dataset']['pool'] in pools_to_remove:
                        raise SmbZfsError(
                            f"Cannot remove pool '{share_info['dataset']['pool']}' as it is used by share '{share_name}'.")
                current_pools = set(self._state.get('secondary_pools', []))
                current_pools -= pools_to_remove
                self._state.set('secondary_pools', sorted(list(current_pools)))
                logger.info("Removed secondary pools: %s",
                            ", ".join(remove_pools))

            simple_updates = {
                'server_name': server_name,
                'workgroup': workgroup,
                'macos_optimized': macos_optimized,
                'default_home_quota': default_home_quota
            }
            for key, value in simple_updates.items():
                if value is not None:
                    if key == 'default_home_quota' and str(value).lower() == 'none':
                        value = 'none'
                    self._state.set(key, value)
                    logger.info(
                        "Updated setup parameter '%s' to '%s'.", key, value)
                    config_needs_update = True

            if config_needs_update:
                logger.info(
                    "Rebuilding Samba configuration due to setup changes.")
                self._config.create_smb_conf(
                    self._state.get("primary_pool"),
                    self._state.get("server_name"),
                    self._state.get("workgroup"),
                    self._state.get("macos_optimized")
                )
                all_shares = self.list_items("shares")
                for share_name, share_info in all_shares.items():
                    self._config.add_share_to_conf(share_name, share_info)

                self._system.test_samba_config()
                self._system.reload_samba()
        except Exception as e:
            self._state.data = original_state
            self._state.save()
            logger.error(
                "Error during setup modification: %s. State restored, but filesystem changes might need manual rollback.", e)
            raise

        logger.info("Global setup modified successfully.")
        return {"msg": "Global setup modified successfully.", "state": self._state.get_data_copy()}

    @requires_initialization
    def modify_home(self, username: str, quota: str) -> Dict[str, Any]:
        """Modifies the quota for a user's home directory."""
        logger.info("Modifying home directory for user '%s'.", username)
        user_info = self._state.get_item("users", username)
        if not user_info:
            raise StateItemNotFoundError("user", username)
        if "dataset" not in user_info or "name" not in user_info["dataset"]:
            raise SmbZfsError(
                f"User '{username}' does not have a managed home directory.")

        home_dataset = user_info["dataset"]["name"]
        if quota:
            self._validate_quota(quota)
        new_quota = quota if quota and quota.lower() != 'none' else 'none'

        logger.info("Setting quota on '%s' to '%s'.", home_dataset, new_quota)
        self._zfs.set_quota(home_dataset, new_quota)
        user_info["dataset"]["quota"] = new_quota
        self._state.set_item("users", username, user_info)

        return {"msg": f"Quota for user '{username}' has been set to {quota}.", "state": self._state.get_data_copy()}

    @requires_initialization
    def change_password(self, username: str, new_password: str) -> Dict[str, Any]:
        """Changes the password for a user."""
        logger.info("Changing password for user '%s'.", username)
        user_info = self._state.get_item("users", username)
        if not user_info:
            raise StateItemNotFoundError("user", username)

        if user_info.get("shell_access"):
            logger.debug("Setting system password for '%s'.", username)
            self._system.set_system_password(username, new_password)

        logger.debug("Setting Samba password for '%s'.", username)
        self._system.set_samba_password(username, new_password)

        return {"msg": f"Password changed successfully for user '{username}'.", "state": self._state.get_data_copy()}

    @requires_initialization
    def get_state(self) -> Dict[str, Any]:
        """Returns a copy of the current state data."""
        logger.debug("Retrieving current system state.")
        return self._state.get_data_copy()

    @requires_initialization
    def list_items(self, category: str) -> Dict[str, Any]:
        """Lists all items within a given category (users, groups, shares, pools)."""
        logger.debug("Listing items for category: %s", category)
        if category not in ["users", "groups", "shares", "pools"]:
            raise SmbZfsError("Invalid category to list.")

        if category == "pools":
            return {
                "primary_pool": self._state.get("primary_pool"),
                "secondary_pools": self._state.get("secondary_pools", [])
            }

        items = self._state.list_items(category)
        if category in ["users", "shares"]:
            for name, data in items.items():
                if "dataset" in data and "name" in data["dataset"]:
                    quota = self._zfs.get_quota(data["dataset"]["name"])
                    data["dataset"]["quota"] = quota if quota and quota != 'none' else "none"
        return items

    def remove(self, delete_data: bool = False, delete_users_and_groups: bool = False) -> Dict[str, Any]:
        """Removes all configurations, services, and optionally all data."""
        logger.warning("Starting full system removal process.")
        if not self._state.is_initialized():
            logger.info("System is not set up, nothing to remove.")
            return {"msg": "System is not set up, nothing to do.", "state": self._state.get_data_copy()}

        primary_pool = self._state.get("primary_pool")
        users = self.list_items("users")
        groups = self.list_items("groups")
        shares = self.list_items("shares")

        if delete_users_and_groups:
            logger.warning(
                "Deleting all managed users and groups from the system.")
            for username in users:
                if self._system.samba_user_exists(username):
                    self._system.delete_samba_user(username)
                if self._system.user_exists(username):
                    self._system.delete_system_user(username)
            for groupname in groups:
                if self._system.group_exists(groupname):
                    self._system.delete_system_group(groupname)

        if delete_data:
            logger.warning("Deleting all managed ZFS datasets.")
            for item_info in shares.values():
                if "dataset" in item_info:
                    self._zfs.destroy_dataset(item_info["dataset"]["name"])
            for item_info in users.values():
                if "dataset" in item_info:
                    self._zfs.destroy_dataset(item_info["dataset"]["name"])

            if self._zfs.dataset_exists(f"{primary_pool}/homes"):
                self._zfs.destroy_dataset(f"{primary_pool}/homes")
            if not self._config.restore_initial_state(SMB_CONF):
                self._system.delete_gracefully(SMB_CONF)

        logger.info("Stopping and disabling services.")
        self._system.stop_services()
        self._system.disable_services()
        self._config.restore_initial_state(AVAHI_SMB_SERVICE)
        self._system.delete_gracefully(self._state.path)

        logger.info("System removal completed successfully.")
        return {"msg": "Removal completed successfully.", "state": {}}
