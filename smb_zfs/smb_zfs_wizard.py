#!/usr/bin/env python3

import argparse
import socket
import sys
from importlib import metadata

from .smb_zfs import SmbZfsManager
from .errors import SmbZfsError
from .const import NAME
from .utils import prompt_for_password, confirm_destructive_action, handle_exception, check_root


def prompt(message, default=None):
    """General purpose prompt that handles KeyboardInterrupt."""
    try:
        if default:
            return input(f"{message} [{default}]: ") or default
        return input(f"{message}: ")
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(130)  # Exit code 130 for user interrupt


def prompt_yes_no(message, default="n"):
    """Prompts for a yes/no answer."""
    options = "[y/N]" if default.lower() == "n" else "[Y/n]"
    while True:
        response = prompt(f"{message} {options} ", default=default).lower()
        if response in ["y", "yes"]:
            return True
        if response in ["n", "no"]:
            return False
        print("Please answer 'yes' or 'no'.")


def _list_and_prompt(manager, item_type, prompt_message, allow_empty=False):
    """Helper to list items and then prompt for a choice."""
    try:
        if item_type == "pools":
            items = [manager._state.get('primary_pool')] + \
                manager._state.get('secondary_pools', [])
        else:
            items = list(manager.list_items(item_type).keys())

        if not items:
            if not allow_empty:
                print(f"No managed {item_type} found.")
                return None
        else:
            print(f"Available {item_type}:", ", ".join(items))
    except SmbZfsError as e:
        if "not set up" in str(e):
            print(
                f"Note: Cannot list {item_type} as system is not yet set up.")
        else:
            raise e

    return prompt(prompt_message)


@handle_exception
def wizard_setup(manager, args=None):
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

    secondary_pools_str = prompt(
        "Enter comma-separated secondary pools (optional)")
    secondary_pools = [p.strip() for p in secondary_pools_str.split(
        ',')] if secondary_pools_str else []

    server_name = prompt(
        "Enter the server's NetBIOS name", default=socket.gethostname()
    )
    workgroup = prompt("Enter the workgroup name", default="WORKGROUP")
    macos_optimized = prompt_yes_no(
        "Enable macOS compatibility optimizations?", default="n"
    )
    default_home_quota = prompt(
        "Enter a default quota for user homes (e.g., 10G, optional)")

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
        result = manager.setup(
            primary_pool, secondary_pools, server_name, workgroup, macos_optimized, default_home_quota)
        print(f"\nSuccess: {result}")


@handle_exception
def wizard_create_user(manager, args=None):
    check_root()
    print("\n--- Create New User Wizard ---")
    username = prompt("Enter the new username")
    if not username:
        raise ValueError("Username cannot be empty.")

    password = prompt_for_password(username)
    allow_shell = prompt_yes_no(
        "Allow shell access (/bin/bash)?", default="n")
    create_home = prompt_yes_no(
        "Create a home directory for this user?", default="y")

    groups_str = _list_and_prompt(
        manager, "groups", "Enter comma-separated groups to add user to (optional)", allow_empty=True)
    groups = [g.strip()
              for g in groups_str.split(",")] if groups_str else []

    result = manager.create_user(
        username, password, allow_shell, groups, create_home)
    print(f"\nSuccess: {result}")


@handle_exception
def wizard_create_share(manager, args=None):
    check_root()
    print("\n--- Create New Share Wizard ---")
    share_name = prompt("Enter the name for the new share")
    if not share_name:
        raise ValueError("Share name cannot be empty.")

    primary_pool = manager._state.get('primary_pool')
    pool = _list_and_prompt(
        manager, "pools", f"Enter the pool for the share (default: {primary_pool})") or primary_pool

    dataset_path = prompt(
        f"Enter the ZFS dataset path within the pool '{pool}' (e.g., data/media)"
    )
    if not dataset_path:
        raise ValueError("Dataset path cannot be empty.")

    comment = prompt("Enter a comment for the share (optional)")
    owner = _list_and_prompt(
        manager, "users", "Enter the owner for the share's files (default: root)", allow_empty=True) or 'root'
    group = _list_and_prompt(
        manager, "groups", "Enter the group for the share's files (default: smb_users)", allow_empty=True) or 'smb_users'

    perms = prompt(
        "Enter file system permissions for the share root", default="0775"
    )
    valid_users = prompt(
        "Enter valid users/groups (e.g., @smb_users)", default=f"@{group}"
    )
    read_only = prompt_yes_no("Make the share read-only?", default="n")
    browseable = prompt_yes_no("Make the share browseable?", default="y")
    quota = prompt(
        "Enter a ZFS quota for this share (e.g., 100G, optional)")

    result = manager.create_share(
        share_name,
        dataset_path,
        owner,
        group,
        perms,
        comment,
        valid_users,
        read_only,
        browseable,
        quota,
        pool
    )
    print(f"\nSuccess: {result}")


@handle_exception
def wizard_create_group(manager, args=None):
    check_root()
    print("\n--- Create New Group Wizard ---")
    group_name = prompt("Enter the name for the new group")
    if not group_name:
        raise ValueError("Group name cannot be empty.")

    description = prompt("Enter a description for the group (optional)")
    users_str = _list_and_prompt(
        manager, "users", "Enter comma-separated initial members (optional)", allow_empty=True)
    users = [u.strip() for u in users_str.split(",")] if users_str else []

    result = manager.create_group(group_name, description, users)
    print(f"\nSuccess: {result}")


@handle_exception
def wizard_modify_group(manager, args=None):
    check_root()
    print("\n--- Modify Group Wizard ---")
    group_name = _list_and_prompt(
        manager, "groups", "Enter the name of the group to modify")
    if not group_name:
        return

    add_users_str = _list_and_prompt(
        manager, "users", "Enter comma-separated users to ADD (optional)", allow_empty=True)
    add_users = [u.strip() for u in add_users_str.split(',')
                 ] if add_users_str else None

    remove_users_str = _list_and_prompt(
        manager, "users", "Enter comma-separated users to REMOVE (optional)", allow_empty=True)
    remove_users = [u.strip() for u in remove_users_str.split(
        ',')] if remove_users_str else None

    if not add_users and not remove_users:
        print("No changes specified. Exiting.")
        return

    result = manager.modify_group(group_name, add_users, remove_users)
    print(f"\nSuccess: {result}")


@handle_exception
def wizard_modify_share(manager, args=None):
    check_root()
    print("\n--- Modify Share Wizard ---")
    share_name = _list_and_prompt(
        manager, "shares", "Enter the name of the share to modify")
    if not share_name:
        return

    print("Enter new values or press Enter to keep the current value.")
    share_info = manager.list_items("shares").get(share_name, {})
    if not share_info:
        raise SmbZfsError(f"Share '{share_name}' not found.")

    kwargs = {}

    current_pool = share_info.get('dataset', {}).get('pool')
    if prompt_yes_no(f"Move share from pool '{current_pool}'?", 'n'):
        kwargs['pool'] = _list_and_prompt(
            manager, "pools", "Select the new pool")

    kwargs['comment'] = prompt(
        "Comment", default=share_info.get('smb_config', {}).get('comment'))
    kwargs['owner'] = _list_and_prompt(
        manager, "users", f"Owner [{share_info.get('system', {}).get('owner')}]", allow_empty=True) or share_info.get('system', {}).get('owner')
    kwargs['group'] = _list_and_prompt(
        manager, "groups", f"Group [{share_info.get('system', {}).get('group')}]", allow_empty=True) or share_info.get('system', {}).get('group')
    kwargs['permissions'] = prompt(
        "Permissions", default=share_info.get('system', {}).get('permissions'))
    kwargs['valid_users'] = prompt(
        "Valid Users", default=share_info.get('smb_config', {}).get('valid_users'))
    kwargs['read_only'] = prompt_yes_no(
        "Read-only?", 'y' if share_info.get('smb_config', {}).get('read_only') else 'n')
    kwargs['browseable'] = prompt_yes_no(
        "Browseable?", 'y' if share_info.get('smb_config', {}).get('browseable') else 'n')
    kwargs['quota'] = prompt(
        "Quota (e.g., 200G or 'none')", default=share_info.get('dataset', {}).get('quota'))

    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    if not kwargs:
        print("No changes were made.")
        return

    result = manager.modify_share(share_name, **kwargs)
    print(f"\nSuccess: {result}")


@handle_exception
def wizard_modify_setup(manager, args=None):
    check_root()
    print("\n--- Modify Global Setup Wizard ---")
    print("Enter new values or press Enter to keep the current value.")

    current_state = {
        'primary_pool': manager._state.get('primary_pool'),
        'secondary_pools': manager._state.get('secondary_pools', []),
        'server_name': manager._state.get('server_name'),
        'workgroup': manager._state.get('workgroup'),
        'macos_optimized': manager._state.get('macos_optimized'),
        'default_home_quota': manager._state.get('default_home_quota'),
    }

    kwargs = {}
    move_data = False

    available_pools = manager._zfs.list_pools()
    print("Available ZFS pools:", ", ".join(available_pools))
    new_primary_pool = prompt("Primary Pool", default=current_state['primary_pool'])
    if new_primary_pool != current_state['primary_pool']:
        kwargs['primary_pool'] = new_primary_pool
        move_data = prompt_yes_no(
            f"Move all datasets from '{current_state['primary_pool']}' to '{new_primary_pool}'?", 'n')

    new_secondary_pools_str = prompt(
        f"Secondary Pools", default=", ".join(current_state['secondary_pools']))
    new_secondary_pools = [p.strip() for p in new_secondary_pools_str.split(
        ',')] if new_secondary_pools_str else []

    pools_to_add = list(set(new_secondary_pools) -
                        set(current_state['secondary_pools']))
    pools_to_remove = list(
        set(current_state['secondary_pools']) - set(new_secondary_pools))
    if pools_to_add:
        kwargs['add_secondary_pools'] = pools_to_add
    if pools_to_remove:
        kwargs['remove_secondary_pools'] = pools_to_remove

    kwargs['server_name'] = prompt(
        "Server Name", default=current_state['server_name'])
    kwargs['workgroup'] = prompt(
        "Workgroup", default=current_state['workgroup'])
    kwargs['macos_optimized'] = prompt_yes_no(
        "macOS Optimized?", 'y' if current_state['macos_optimized'] else 'n')
    kwargs['default_home_quota'] = prompt("Default Home Quota (e.g., 50G or 'none')",
                                          default=current_state['default_home_quota'] or 'none')

    # Filter out non-changes
    final_kwargs = {}
    for k, v in kwargs.items():
        if k in ['add_secondary_pools', 'remove_secondary_pools'] and v:
            final_kwargs[k] = v
        elif k not in ['add_secondary_pools', 'remove_secondary_pools'] and v != current_state.get(k):
            final_kwargs[k] = v

    if not final_kwargs:
        print("No changes were made.")
        return

    result = manager.modify_setup(move_data=move_data, **final_kwargs)
    print(f"\nSuccess: {result}")


@handle_exception
def wizard_modify_home(manager, args=None):
    check_root()
    print("\n--- Modify Home Quota Wizard ---")
    username = _list_and_prompt(
        manager, "users", "Enter the user whose home you want to modify")
    if not username:
        return

    user_info = manager.list_items("users").get(username, {})
    dataset_info = user_info.get('dataset')

    if not dataset_info:
        raise SmbZfsError(
            f"Could not find dataset info for user '{username}'.")

    current_quota = manager._zfs.get_quota(dataset_info['name'])
    new_quota = prompt(
        f"Enter new quota for {username}'s home (e.g., 25G or 'none')", default=current_quota)

    result = manager.modify_home(username, new_quota)
    print(f"\nSuccess: {result}")


@handle_exception
def wizard_delete_user(manager, args=None):
    check_root()
    print("\n--- Delete User Wizard ---")
    username = _list_and_prompt(
        manager, "users", "Enter the username to delete")
    if not username:
        return

    delete_data = prompt_yes_no(
        f"Delete user '{username}'s home directory and all its data?", default="n"
    )

    if delete_data:
        if not confirm_destructive_action(
            f"This will PERMANENTLY delete user '{username}' AND their home directory.",
            False
        ):
            return

    result = manager.delete_user(username, delete_data)
    print(f"\nSuccess: {result}")


@handle_exception
def wizard_delete_share(manager, args=None):
    check_root()
    print("\n--- Delete Share Wizard ---")
    share_name = _list_and_prompt(
        manager, "shares", "Enter the name of the share to delete")
    if not share_name:
        return

    delete_data = prompt_yes_no(
        f"Delete the ZFS dataset for share '{share_name}' and all its data?",
        default="n",
    )

    if delete_data:
        if not confirm_destructive_action(
            f"This will PERMANENTLY delete the ZFS dataset for share '{share_name}'.",
            False
        ):
            return

    result = manager.delete_share(share_name, delete_data)
    print(f"\nSuccess: {result}")


@handle_exception
def wizard_delete_group(manager, args=None):
    check_root()
    print("\n--- Delete Group Wizard ---")
    group_name = _list_and_prompt(
        manager, "groups", "Enter the name of the group to delete")
    if not group_name:
        return

    result = manager.delete_group(group_name)
    print(f"\nSuccess: {result}")


@handle_exception
def wizard_remove(manager, args=None):
    check_root()
    print("\n--- Remove Setup Wizard ---")
    delete_data = prompt_yes_no(
        "Delete ALL ZFS datasets created by this tool (user homes, shares)?",
        default="n",
    )
    delete_users = prompt_yes_no(
        "Delete ALL users and groups created by this tool?", default="n"
    )

    message = "This will remove all configurations and potentially all user data and users created by this tool."
    if confirm_destructive_action(message, False):
        result = manager.remove(delete_data, delete_users)
        print(f"\nSuccess: {result}")


def main():
    """Main function to run the wizard."""
    parser = argparse.ArgumentParser(
        prog=f"{NAME}-wizard",
        description="An interactive wizard to manage Samba on a ZFS-backed system.",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"{metadata.version(NAME)}"
    )
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands")
    subparsers.required = True

    p_setup = subparsers.add_parser(
        "setup", help="Start the wizard to set up and configure Samba, ZFS, and Avahi.")
    p_setup.set_defaults(func=wizard_setup)

    p_create = subparsers.add_parser(
        "create", help="Start the wizard to create a new user, share, or group.")
    create_sub = p_create.add_subparsers(dest="create_type", required=True)
    p_create_user = create_sub.add_parser(
        "user", help="Start the new user wizard.")
    p_create_user.set_defaults(func=wizard_create_user)
    p_create_share = create_sub.add_parser(
        "share", help="Start the new share wizard.")
    p_create_share.set_defaults(func=wizard_create_share)
    p_create_group = create_sub.add_parser(
        "group", help="Start the new group wizard.")
    p_create_group.set_defaults(func=wizard_create_group)

    p_modify = subparsers.add_parser(
        "modify", help="Start the wizard to modify an existing user, share, or group.")
    modify_sub = p_modify.add_subparsers(dest="modify_type", required=True)
    p_modify_group = modify_sub.add_parser(
        "group", help="Start the modify group wizard.")
    p_modify_group.set_defaults(func=wizard_modify_group)
    p_modify_share = modify_sub.add_parser(
        "share", help="Start the modify share wizard.")
    p_modify_share.set_defaults(func=wizard_modify_share)
    p_modify_setup = modify_sub.add_parser(
        "setup", help="Start the modify global setup wizard.")
    p_modify_setup.set_defaults(func=wizard_modify_setup)
    p_modify_home = modify_sub.add_parser(
        "home", help="Start the modify home wizard.")
    p_modify_home.set_defaults(func=wizard_modify_home)

    p_delete = subparsers.add_parser(
        "delete", help="Start the wizard to delete a user, share, or group.")
    delete_sub = p_delete.add_subparsers(dest="delete_type", required=True)
    p_delete_user = delete_sub.add_parser(
        "user", help="Start the delete user wizard.")
    p_delete_user.set_defaults(func=wizard_delete_user)
    p_delete_share = delete_sub.add_parser(
        "share", help="Start the delete share wizard."
    )
    p_delete_share.set_defaults(func=wizard_delete_share)
    p_delete_group = delete_sub.add_parser(
        "group", help="Start the delete group wizard."
    )
    p_delete_group.set_defaults(func=wizard_delete_group)

    p_remove = subparsers.add_parser(
        "remove", help="Start the wizard to uninstall smb-zfs."
    )
    p_remove.set_defaults(func=wizard_remove)

    args = parser.parse_args()

    try:
        manager = SmbZfsManager()
        args.func(manager, args)
    except SmbZfsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
