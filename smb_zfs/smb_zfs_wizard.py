import argparse
import socket
import sys
from typing import Optional, Dict, Any

from .smb_zfs import SmbZfsManager
from .errors import SmbZfsError
from .utils import prompt_for_password, confirm_destructive_action, handle_exception, check_root


def prompt(message: str, default: Optional[str] = None) -> str:
    """Prompts the user for input and handles KeyboardInterrupt gracefully."""
    try:
        if default:
            return input(f"{message} [{default}]: ") or default
        return input(f"{message}: ")
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(130)

def prompt_yes_no(message: str, default: str = "n") -> bool:
    """Prompts the user for a yes/no answer."""
    options = "[y/N]" if default.lower() == "n" else "[Y/n]"
    while True:
        response = prompt(f"{message} {options} ", default=default).lower()
        if response in ["y", "yes"]:
            return True
        if response in ["n", "no"]:
            return False
        print("Please answer 'yes' or 'no'.")

def _list_and_prompt(manager: SmbZfsManager, item_type: str, prompt_message: str, allow_empty: bool = False) -> str:
    """A helper to list items of a certain type and then prompt for a choice."""
    try:
        if item_type == "pools":
            items = [manager._state.get('primary_pool')] + manager._state.get('secondary_pools', [])
            items = [p for p in items if p] # Filter out None
        else:
            items = list(manager.list_items(item_type).keys())
        
        if not items:
            if not allow_empty:
                print(f"No managed {item_type} found.")
                return ""
        else:
            print(f"Available {item_type}:", ", ".join(items))

    except SmbZfsError as e:
        if "not set up" in str(e):
            print(f"Note: Cannot list {item_type} as system is not yet set up.")
        else:
            raise e
    return prompt(prompt_message)

@handle_exception
def wizard_setup(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard for the initial system setup."""
    check_root()
    print("\n--- Initial System Setup Wizard ---")
    available_pools = manager._zfs.list_pools()
    if available_pools:
        print("Available ZFS pools:", ", ".join(available_pools))
    else:
        print("Warning: No ZFS pools found.")

    primary_pool = prompt("Enter the name of the ZFS primary pool to use")
    if not primary_pool:
        raise ValueError("Primary pool name cannot be empty.")
    
    secondary_pools_str = prompt("Enter comma-separated secondary pools (optional)")
    secondary_pools = [p.strip() for p in secondary_pools_str.split(',')] if secondary_pools_str else []
    
    server_name = prompt("Enter the server's NetBIOS name", default=socket.gethostname())
    workgroup = prompt("Enter the workgroup name", default="WORKGROUP")
    macos_optimized = prompt_yes_no("Enable macOS compatibility optimizations?", default="n")
    default_home_quota = prompt("Enter a default quota for user homes (e.g., 10G, optional)")

    print("\nSummary of actions:")
    print(f" - ZFS Primary Pool: {primary_pool}")
    if secondary_pools:
        print(f" - ZFS Secondary Pools: {', '.join(secondary_pools)}")
    print(f" - Server Name: {server_name}")
    print(f" - Workgroup: {workgroup}")
    print(f" - macOS Optimized: {macos_optimized}")
    if default_home_quota:
        print(f" - Default Home Quota: {default_home_quota}")

    if prompt_yes_no("Proceed with setup?", default="y"):
        result = manager.setup(primary_pool, secondary_pools, server_name, workgroup, macos_optimized, default_home_quota)
        print(f"\nSuccess: {result['msg']}")

@handle_exception
def wizard_create_user(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard to create a new user."""
    check_root()
    print("\n--- Create New User Wizard ---")
    username = prompt("Enter the new username")
    if not username:
        raise ValueError("Username cannot be empty.")
    
    password = prompt_for_password(username)
    allow_shell = prompt_yes_no("Allow shell access (/bin/bash)?", default="n")
    create_home = prompt_yes_no("Create a home directory for this user?", default="y")
    groups_str = _list_and_prompt(manager, "groups", "Enter comma-separated groups to add user to (optional)", allow_empty=True)
    groups = [g.strip() for g in groups_str.split(",")] if groups_str else []
    
    result = manager.create_user(username, password, allow_shell, groups, create_home)
    print(f"\nSuccess: {result['msg']}")

@handle_exception
def wizard_create_share(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard to create a new share."""
    check_root()
    print("\n--- Create New Share Wizard ---")
    share_name = prompt("Enter the name for the new share")
    if not share_name:
        raise ValueError("Share name cannot be empty.")

    primary_pool = manager._state.get('primary_pool')
    pool = _list_and_prompt(manager, "pools", f"Enter the pool for the share (default: {primary_pool})") or primary_pool
    dataset_path = prompt(f"Enter the ZFS dataset path within the pool '{pool}' (e.g., data/media)")
    if not dataset_path:
        raise ValueError("Dataset path cannot be empty.")

    comment = prompt("Enter a comment for the share (optional)")
    owner = _list_and_prompt(manager, "users", "Enter the owner for the share's files (default: root)", allow_empty=True) or 'root'
    group = _list_and_prompt(manager, "groups", "Enter the group for the share's files (default: smb_users)", allow_empty=True) or 'smb_users'
    perms = prompt("Enter file system permissions for the share root", default="0775")
    valid_users = prompt("Enter valid users/groups (e.g., @smb_users)", default=f"@{group}")
    read_only = prompt_yes_no("Make the share read-only?", default="n")
    browseable = prompt_yes_no("Make the share browseable?", default="y")
    quota = prompt("Enter a ZFS quota for this share (e.g., 100G, optional)")

    result = manager.create_share(share_name, dataset_path, owner, group, perms, comment, valid_users, read_only, browseable, quota, pool)
    print(f"\nSuccess: {result['msg']}")

@handle_exception
def wizard_create_group(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard to create a new group."""
    check_root()
    print("\n--- Create New Group Wizard ---")
    group_name = prompt("Enter the name for the new group")
    if not group_name:
        raise ValueError("Group name cannot be empty.")
    
    description = prompt("Enter a description for the group (optional)")
    users_str = _list_and_prompt(manager, "users", "Enter comma-separated initial members (optional)", allow_empty=True)
    users = [u.strip() for u in users_str.split(",")] if users_str else []
    
    result = manager.create_group(group_name, description, users)
    print(f"\nSuccess: {result['msg']}")

@handle_exception
def wizard_modify_group(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard to modify a group."""
    check_root()
    print("\n--- Modify Group Wizard ---")
    group_name = _list_and_prompt(manager, "groups", "Enter the name of the group to modify")
    if not group_name:
        return

    add_users_str = _list_and_prompt(manager, "users", "Enter comma-separated users to ADD (optional)", allow_empty=True)
    add_users = [u.strip() for u in add_users_str.split(',')] if add_users_str else None
    
    remove_users_str = _list_and_prompt(manager, "users", "Enter comma-separated users to REMOVE (optional)", allow_empty=True)
    remove_users = [u.strip() for u in remove_users_str.split(',')] if remove_users_str else None

    if not add_users and not remove_users:
        print("No changes specified. Exiting.")
        return
        
    result = manager.modify_group(group_name, add_users, remove_users)
    print(f"\nSuccess: {result['msg']}")

@handle_exception
def wizard_modify_share(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard to modify a share."""
    check_root()
    print("\n--- Modify Share Wizard ---")
    share_name = _list_and_prompt(manager, "shares", "Enter the name of the share to modify")
    if not share_name:
        return

    print("Enter new values or press Enter to keep the current value.")
    share_info = manager.list_items("shares").get(share_name)
    if not share_info:
        raise SmbZfsError(f"Share '{share_name}' not found.")

    # Collect new values
    new_name = None
    if prompt_yes_no(f"Rename share '{share_name}'?", 'n'):
        new_name = prompt("Enter new share name")

    new_pool = None
    if prompt_yes_no(f"Move share from pool '{share_info.get('dataset', {}).get('pool')}'?", 'n'):
        new_pool = _list_and_prompt(manager, "pools", "Select the new pool")

    new_comment = prompt("Comment", default=share_info.get('smb_config', {}).get('comment'))
    new_owner = _list_and_prompt(manager, "users", f"Owner [{share_info.get('system', {}).get('owner')}]", allow_empty=True)
    new_group = _list_and_prompt(manager, "groups", f"Group [{share_info.get('system', {}).get('group')}]", allow_empty=True)
    new_permissions = prompt("Permissions", default=share_info.get('system', {}).get('permissions'))
    new_valid_users = prompt("Valid Users", default=share_info.get('smb_config', {}).get('valid_users'))
    new_read_only = prompt_yes_no("Read-only?", 'y' if share_info.get('smb_config', {}).get('read_only') else 'n')
    new_browseable = prompt_yes_no("Browseable?", 'y' if share_info.get('smb_config', {}).get('browseable') else 'n')
    new_quota = prompt("Quota (e.g., 200G or 'none')", default=share_info.get('dataset', {}).get('quota'))
    
    # Call manager with explicit named arguments
    result = manager.modify_share(
        share_name=share_name,
        name=new_name,
        pool=new_pool,
        comment=new_comment,
        owner=new_owner or None, # Pass None if empty
        group=new_group or None, # Pass None if empty
        permissions=new_permissions,
        valid_users=new_valid_users,
        read_only=new_read_only,
        browseable=new_browseable,
        quota=new_quota
    )
    print(f"\nSuccess: {result['msg']}")

@handle_exception
def wizard_modify_setup(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard to modify the global setup."""
    check_root()
    print("\n--- Modify Global Setup Wizard ---")
    print("Enter new values or press Enter to keep the current value.")
    
    current_state = manager.get_state()
    
    available_pools = manager._zfs.list_pools()
    print("Available ZFS pools:", ", ".join(available_pools))
    
    # Collect new values
    new_primary_pool = prompt("Primary Pool", default=current_state.get('primary_pool'))
    
    current_secondary = current_state.get('secondary_pools', [])
    new_secondary_pools_str = prompt("Secondary Pools", default=",".join(current_secondary))
    new_secondary_pools = [p.strip() for p in new_secondary_pools_str.split(',')] if new_secondary_pools_str else []
    
    pools_to_add = list(set(new_secondary_pools) - set(current_secondary))
    pools_to_remove = list(set(current_secondary) - set(new_secondary_pools))
    
    new_server_name = prompt("Server Name", default=current_state.get('server_name'))
    new_workgroup = prompt("Workgroup", default=current_state.get('workgroup'))
    new_macos_optimized = prompt_yes_no("macOS Optimized?", 'y' if current_state.get('macos_optimized') else 'n')
    new_default_home_quota = prompt("Default Home Quota (e.g., 50G or 'none')", default=current_state.get('default_home_quota') or 'none')

    # Call manager with explicit named arguments
    result = manager.modify_setup(
        primary_pool=new_primary_pool,
        add_secondary_pools=pools_to_add or None,
        remove_secondary_pools=pools_to_remove or None,
        server_name=new_server_name,
        workgroup=new_workgroup,
        macos_optimized=new_macos_optimized,
        default_home_quota=new_default_home_quota
    )
    print(f"\nSuccess: {result['msg']}")

@handle_exception
def wizard_modify_home(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard to modify a user's home directory quota."""
    check_root()
    print("\n--- Modify Home Quota Wizard ---")
    username = _list_and_prompt(manager, "users", "Enter the user whose home you want to modify")
    if not username:
        return

    user_info = manager.list_items("users").get(username, {})
    dataset_info = user_info.get('dataset')
    if not dataset_info:
        raise SmbZfsError(f"Could not find dataset info for user '{username}'.")
    
    current_quota = manager._zfs.get_quota(dataset_info['name'])
    new_quota = prompt(f"Enter new quota for {username}'s home (e.g., 25G or 'none')", default=current_quota)
    
    result = manager.modify_home(username, new_quota)
    print(f"\nSuccess: {result['msg']}")

@handle_exception
def wizard_delete_user(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard to delete a user."""
    check_root()
    print("\n--- Delete User Wizard ---")
    username = _list_and_prompt(manager, "users", "Enter the username to delete")
    if not username:
        return
    
    delete_data = prompt_yes_no(f"Delete user '{username}'s home directory and all its data?", default="n")
    if delete_data:
        if not confirm_destructive_action(f"This will PERMANENTLY delete user '{username}' AND their home directory.", False):
            return
            
    result = manager.delete_user(username, delete_data)
    print(f"\nSuccess: {result['msg']}")

@handle_exception
def wizard_delete_share(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard to delete a share."""
    check_root()
    print("\n--- Delete Share Wizard ---")
    share_name = _list_and_prompt(manager, "shares", "Enter the name of the share to delete")
    if not share_name:
        return
        
    delete_data = prompt_yes_no(f"Delete the ZFS dataset for share '{share_name}' and all its data?", default="n")
    if delete_data:
        if not confirm_destructive_action(f"This will PERMANENTLY delete the ZFS dataset for share '{share_name}'.", False):
            return
            
    result = manager.delete_share(share_name, delete_data)
    print(f"\nSuccess: {result['msg']}")

@handle_exception
def wizard_delete_group(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard to delete a group."""
    check_root()
    print("\n--- Delete Group Wizard ---")
    group_name = _list_and_prompt(manager, "groups", "Enter the name of the group to delete")
    if not group_name:
        return
        
    result = manager.delete_group(group_name)
    print(f"\nSuccess: {result['msg']}")

@handle_exception
def wizard_remove(manager: SmbZfsManager, args: Optional[argparse.Namespace] = None) -> None:
    """Runs an interactive wizard to remove the entire smb-zfs setup."""
    check_root()
    print("\n--- Remove Setup Wizard ---")
    delete_data = prompt_yes_no("Delete ALL ZFS datasets created by this tool (user homes, shares)?", default="n")
    delete_users = prompt_yes_no("Delete ALL users and groups created by this tool?", default="n")
    
    message = "This will remove all configurations and potentially all user data and users created by this tool."
    if confirm_destructive_action(message, False):
        result = manager.remove(delete_data, delete_users)
        print(f"\nSuccess: {result['msg']}")

def add_wizard_subparsers(main_subparsers: argparse._SubParsersAction) -> None:
    """Adds the 'wizard' command and its subcommands to the main CLI parser."""
    
    p_wizard = main_subparsers.add_parser('wizard', help='Start an interactive wizard for common tasks.')
    wizard_subparsers = p_wizard.add_subparsers(dest='wizard_command', help='Available wizards', required=True)

    wizards = {
        "setup": (wizard_setup, "Start the wizard to set up and configure Samba, ZFS, and Avahi."),
        "create user": (wizard_create_user, "Start the new user wizard."),
        "create share": (wizard_create_share, "Start the new share wizard."),
        "create group": (wizard_create_group, "Start the new group wizard."),
        "modify group": (wizard_modify_group, "Start the modify group wizard."),
        "modify share": (wizard_modify_share, "Start the modify share wizard."),
        "modify setup": (wizard_modify_setup, "Start the modify global setup wizard."),
        "modify home": (wizard_modify_home, "Start the modify home wizard."),
        "delete user": (wizard_delete_user, "Start the delete user wizard."),
        "delete share": (wizard_delete_share, "Start the delete share wizard."),
        "delete group": (wizard_delete_group, "Start the delete group wizard."),
        "remove": (wizard_remove, "Start the wizard to uninstall smb-zfs.")
    }

    # Dynamically create parsers
    cmd_parsers: Dict[str, Any] = {}
    for cmd_str, (func, help_text) in wizards.items():
        parts = cmd_str.split()
        if len(parts) == 1:
            p = wizard_subparsers.add_parser(parts[0], help=help_text)
            p.set_defaults(func=func)
            cmd_parsers[parts[0]] = p
        else:
            parent_name = parts[0]
            child_name = parts[1]
            if parent_name not in cmd_parsers:
                parent_parser = wizard_subparsers.add_parser(parent_name, help=f"Start a wizard to {parent_name} an item.")
                cmd_parsers[parent_name] = parent_parser.add_subparsers(dest=f"{parent_name}_type", required=True)
            
            p = cmd_parsers[parent_name].add_parser(child_name, help=help_text)
            p.set_defaults(func=func)
