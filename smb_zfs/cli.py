#!/usr/bin/env python3
import argparse
import getpass
import json
import socket
import sys
import logging
from importlib import metadata
from typing import Any, Dict

from .smb_zfs import SmbZfsManager
from .errors import SmbZfsError
from .const import NAME, SMB_CONF, AVAHI_SMB_SERVICE
from .utils import prompt_for_password, confirm_destructive_action, handle_exception, check_root
from .smb_zfs_wizard import add_wizard_subparsers

# Setup root logger for the application
log = logging.getLogger(__name__.split('.')[0])


def _handle_output(result: Dict[str, Any], args: argparse.Namespace) -> None:
    """Prints result as JSON or plain text based on args."""
    if args.json:
        print(json.dumps(result, indent=2))
    elif 'msg' in result:
        print(result['msg'])


@handle_exception
def cmd_setup(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'setup' command."""
    check_root()
    server_name = args.server_name or socket.gethostname()
    workgroup = args.workgroup or "WORKGROUP"
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print("  - Check for required pkgs: zfsutils-linux, samba, avahi-daemon")
        print(f"  - Create ZFS dataset: {args.primary_pool}/homes")
        print("  - Create system group: smb_users")
        print(f"  - Generate {SMB_CONF} with:")
        print(f"    - Primary Pool: {args.primary_pool}")
        if args.secondary_pools:
            print(f"    - Secondary Pools: {', '.join(args.secondary_pools)}")
        print(f"    - Server Name: {server_name}")
        print(f"    - Workgroup: {workgroup}")
        print(f"    - macOS optimized: {args.macos}")
        if args.default_home_quota:
            print(f"    - Default Home Quota: {args.default_home_quota}")
        print(f"  - Generate {AVAHI_SMB_SERVICE}")
        print("  - Enable and start smbd, nmbd, avahi-daemon services")
        print(f"  - Initialize state file at {manager._state.path}")
        return
    result = manager.setup(args.primary_pool, args.secondary_pools, server_name, workgroup,
                           args.macos, args.default_home_quota)
    _handle_output(result, args)


@handle_exception
def cmd_create_user(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'create user' command."""
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print(f"  - Create system user: {args.user}")
        if not args.no_home:
            print(
                f"  - Create ZFS home dataset: {manager._state.get('primary_pool')}/homes/{args.user}"
            )
            if manager._state.get('default_home_quota'):
                print(
                    f"  - Set ZFS quota: {manager._state.get('default_home_quota')}")
            print("  - Set permissions on home directory")
        print(f"  - Add Samba user: {args.user}")
        print("  - Add user to group 'smb_users'")
        if args.groups:
            print(f"  - Add user to additional groups: {args.groups}")
        print("  - Update state file")
        return
    check_root()
    password = args.password or prompt_for_password(args.user)
    groups = args.groups.split(",") if args.groups else []
    create_home = not args.no_home
    result = manager.create_user(
        args.user, password, args.shell, groups, create_home)
    _handle_output(result, args)


@handle_exception
def cmd_create_share(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'create share' command."""
    if args.dry_run:
        target_pool = args.pool or manager._state.get('primary_pool')
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print(
            f"  - Create ZFS dataset: {target_pool}/{args.dataset}"
        )
        if args.quota:
            print(f"  - Set ZFS quota to {args.quota}")
        print(
            f"  - Set ownership to {args.owner}:{args.group} and permissions to {args.perms}"
        )
        print(f"  - Add share '{args.share}' to {SMB_CONF}")
        print("  - Reload Samba configuration")
        print("  - Update state file")
        return
    check_root()
    result = manager.create_share(
        name=args.share,
        dataset_path=args.dataset,
        owner=args.owner,
        group=args.group,
        perms=args.perms,
        comment=args.comment,
        valid_users=args.valid_users,
        read_only=args.readonly,
        browseable=not args.no_browse,
        quota=args.quota,
        pool=args.pool,
    )
    _handle_output(result, args)


@handle_exception
def cmd_create_group(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'create group' command."""
    users = args.users.split(",") if args.users else []
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print(f"  - Create system group: {args.group}")
        if users:
            print(f"  - Add initial members: {', '.join(users)}")
        print("  - Update state file")
        return
    check_root()
    result = manager.create_group(args.group, args.description, users)
    _handle_output(result, args)


@handle_exception
def cmd_modify_group(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'modify group' command."""
    add_users = args.add_users.split(',') if args.add_users else []
    remove_users = args.remove_users.split(',') if args.remove_users else []
    if args.dry_run:
        print("--- Dry Run ---")
        print(f"Would modify group '{args.group}':")
        if add_users:
            print(f"  - Add users: {', '.join(add_users)}")
        if remove_users:
            print(f"  - Remove users: {', '.join(remove_users)}")
        return
    check_root()
    result = manager.modify_group(args.group, add_users, remove_users)
    _handle_output(result, args)


@handle_exception
def cmd_modify_share(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'modify share' command."""
    modifications = {
        'name': args.name,
        'comment': args.comment,
        'valid_users': args.valid_users,
        'permissions': args.perms,
        'owner': args.owner,
        'group': args.group,
        'quota': args.quota,
        'pool': args.pool,
        'read_only': args.readonly,
        'browseable': args.no_browse
    }
    active_modifications = {k: v for k,
                            v in modifications.items() if v is not None}
    if not active_modifications:
        print("No modifications specified. Use --help to see options.", file=sys.stderr)
        return
    if args.dry_run:
        print("--- Dry Run ---")
        print(f"Would modify share '{args.share}' with the following changes:")
        for key, value in active_modifications.items():
            print(f"  - Set {key} to: {value}")
        return
    check_root()
    result = manager.modify_share(
        args.share,
        name=args.name,
        comment=args.comment,
        valid_users=args.valid_users,
        permissions=args.perms,
        owner=args.owner,
        group=args.group,
        quota=args.quota,
        pool=args.pool,
        read_only=args.readonly,
        browseable=args.no_browse
    )
    _handle_output(result, args)


@handle_exception
def cmd_modify_setup(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'modify setup' command."""
    add_pools = args.add_secondary_pools
    remove_pools = args.remove_secondary_pools
    modifications = {
        "server_name": args.server_name,
        "workgroup": args.workgroup,
        "macos_optimized": args.macos,
        "default_home_quota": args.default_home_quota,
        "primary_pool": args.primary_pool,
        "add_secondary_pools": add_pools,
        "remove_secondary_pools": remove_pools
    }
    active_modifications = {k: v for k,
                            v in modifications.items() if v is not None}
    if not active_modifications:
        print("No modifications specified. Use --help to see options.", file=sys.stderr)
        return
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would modify global setup with the following changes:")
        for key, value in active_modifications.items():
            display_key = 'macos' if key == 'macos_optimized' else key
            print(f"  - Set {display_key} to: {value}")
        return
    check_root()
    result = manager.modify_setup(
        server_name=args.server_name,
        workgroup=args.workgroup,
        macos_optimized=args.macos,
        default_home_quota=args.default_home_quota,
        primary_pool=args.primary_pool,
        add_secondary_pools=add_pools,
        remove_secondary_pools=remove_pools
    )
    _handle_output(result, args)


@handle_exception
def cmd_modify_home(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'modify home' command."""
    if args.dry_run:
        print("--- Dry Run ---")
        print(f"Would modify home for user '{args.user}':")
        print(f"  - Set ZFS quota to: {args.quota}")
        return
    check_root()
    result = manager.modify_home(args.user, args.quota)
    _handle_output(result, args)


@handle_exception
def cmd_delete_user(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'delete user' command."""
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print(f"  - Remove Samba user: {args.user}")
        print(f"  - Remove system user: {args.user}")
        if args.delete_data:
            user_info = manager._state.get_item('users', args.user)
            if user_info and 'dataset' in user_info:
                print(
                    f"  - DESTROY ZFS dataset: {user_info['dataset']['name']}"
                )
            else:
                print(
                    f"  - User '{args.user}' or their dataset not found in state.")
        print("  - Update state file")
        return
    if args.delete_data:
        if not confirm_destructive_action(
            f"This will permanently delete user '{args.user}' AND their home directory.",
            args.yes,
        ):
            print("Operation cancelled.", file=sys.stderr)
            return
    check_root()
    result = manager.delete_user(args.user, args.delete_data)
    _handle_output(result, args)


@handle_exception
def cmd_delete_share(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'delete share' command."""
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print(f"  - Remove share '{args.share}' from {SMB_CONF}")
        if args.delete_data:
            share_info = manager._state.get_item('shares', args.share)
            if share_info and 'dataset' in share_info:
                print(
                    f"  - DESTROY ZFS dataset: {share_info['dataset']['name']}"
                )
            else:
                print(
                    f"  - Share '{args.share}' or its dataset not found in state.")
        print("  - Reload Samba configuration")
        print("  - Update state file")
        return
    if args.delete_data:
        if not confirm_destructive_action(
            f"This will permanently delete the ZFS dataset for share '{args.share}'.",
            args.yes,
        ):
            print("Operation cancelled.", file=sys.stderr)
            return
    check_root()
    result = manager.delete_share(args.share, args.delete_data)
    _handle_output(result, args)


@handle_exception
def cmd_delete_group(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'delete group' command."""
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print(f"  - Remove system group: {args.group}")
        print("  - Update state file")
        return
    check_root()
    result = manager.delete_group(args.group)
    _handle_output(result, args)


@handle_exception
def cmd_list(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'list' command."""
    items = manager.list_items(args.type)
    if not items:
        print(f"No {args.type} found.")
        return
    if args.type == "pools":
        print("--- Primary Pool ---")
        print(f"  {items['primary_pool']}")
        print("\n--- Secondary Pools ---")
        if items['secondary_pools']:
            for pool in items['secondary_pools']:
                print(f"  - {pool}")
        else:
            print("  None")
        return
    for name, data in items.items():
        print(f"--- {name} ---")
        for key, value in data.items():
            if isinstance(value, dict):
                print(f"  {key.replace('_', ' ').capitalize()}:")
                for sub_key, sub_value in value.items():
                    print(
                        f"    - {sub_key.replace('_', ' ').capitalize()}: {sub_value}")
            elif isinstance(value, list):
                value_str = ", ".join(str(v)
                                      for v in value) if value else "None"
                print(f"  {key.replace('_', ' ').capitalize()}: {value_str}")
            else:
                print(f"  {key.replace('_', ' ').capitalize()}: {value}")
        print()


@handle_exception
def cmd_passwd(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'passwd' command."""
    password = prompt_for_password(args.user)
    if getpass.getuser() != args.user:
        check_root()
    result = manager.change_password(args.user, password)
    _handle_output(result, args)


@handle_exception
def cmd_remove(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'remove' command."""
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        if not manager._state.is_initialized():
            print("System is not set up, nothing to do.")
            return
        users = manager.list_items("users")
        groups = manager.list_items("groups")
        shares = manager.list_items("shares")
        if args.delete_users:
            print("  - Delete all managed users:")
            for username in users:
                print(f"    - {username}")
            print("  - Delete all managed groups:")
            for groupname in groups:
                print(f"    - {groupname}")
        if args.delete_data:
            print("  - DESTROY all managed ZFS datasets:")
            for share_info in shares.values():
                if "dataset" in share_info:
                    print(f"    - {share_info['dataset']['name']}")
            for user_info in users.values():
                if "dataset" in user_info:
                    print(f"    - {user_info['dataset']['name']}")
            pool = manager._state.get("primary_pool")
            if pool:
                print(f"    - {pool}/homes")
        print("  - Stop and disable smbd, nmbd, avahi-daemon services.")
        print(
            f"  - Remove configuration files: {SMB_CONF}, {AVAHI_SMB_SERVICE}")
        print(f"  - Remove state file: {manager._state.path}")
        return
    prompt = "This will remove all configurations and potentially all user data and users created by this tool."
    if not confirm_destructive_action(prompt, args.yes):
        print("Operation cancelled.", file=sys.stderr)
        return
    check_root()
    result = manager.remove(args.delete_data, args.delete_users)
    _handle_output(result, args)


@handle_exception
def cmd_get_state(manager: SmbZfsManager, args: argparse.Namespace) -> None:
    """Handler for the 'get-state' command."""
    state = manager.get_state()
    print(json.dumps(state, indent=2))

def create_parser() -> argparse.ArgumentParser:
    """Creates and configures the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog=NAME,
        description="A tool to manage Samba on a ZFS-backed system.",
    )
    parser.add_argument(
        "--version", action="version", version=f"{NAME} {metadata.version('smb_zfs')}"
    )
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="Increase verbosity level (-v for warning, -vv for info, -vvv for debug)."
    )
    
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Available commands"
    )

    # --- Add Wizard Commands ---
    add_wizard_subparsers(subparsers)
    
    # --- Setup Parser ---
    p_setup = subparsers.add_parser(
        "setup", help="Set up and configure Samba, ZFS, and Avahi."
    )
    p_setup.add_argument(
        "--primary-pool", required=True, help="The name of the ZFS pool to use for user homes."
    )
    p_setup.add_argument(
        "--secondary-pools", nargs='*', help="Space-separated list of other ZFS pools for shares."
    )
    p_setup.add_argument(
        "--server-name", help="The server's NetBIOS name (default: hostname)."
    )
    p_setup.add_argument(
        "--workgroup", help="The workgroup name (default: WORKGROUP)."
    )
    p_setup.add_argument(
        "--macos", action="store_true", help="Enable macOS compatibility optimizations."
    )
    p_setup.add_argument(
        "--default-home-quota", help="Set a default quota for user home directories (e.g., 10G)."
    )
    p_setup.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
    )
    p_setup.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_setup.set_defaults(func=cmd_setup)
    
    # --- Create Parser ---
    p_create = subparsers.add_parser(
        "create", help="Create a new user, share, or group."
    )
    create_sub = p_create.add_subparsers(dest="create_type", required=True)
    p_create_user = create_sub.add_parser("user", help="Create a new user.")
    p_create_user.add_argument("user", help="The username to create.")
    p_create_user.add_argument(
        "--password", help="Set the user's password. If omitted, will prompt securely."
    )
    p_create_user.add_argument(
        "--shell",
        action="store_true",
        help="Grant the user a standard shell (/bin/bash).",
    )
    p_create_user.add_argument(
        "--groups", help="A comma-separated list of groups to add the user to."
    )
    p_create_user.add_argument(
        "--no-home",
        action="store_true",
        help="Do not create a home directory for the user.",
    )
    p_create_user.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
    )
    p_create_user.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_create_user.set_defaults(func=cmd_create_user)

    p_create_share = create_sub.add_parser("share", help="Create a new share.")
    p_create_share.add_argument("share", help="The name of the share.")
    p_create_share.add_argument(
        "--dataset",
        required=True,
        help="The path for the ZFS dataset within the pool (e.g., 'data/projects').",
    )
    p_create_share.add_argument(
        "--pool", help="The ZFS pool to create the share in. Defaults to the primary pool."
    )
    p_create_share.add_argument(
        "--comment", default="", help="A description for the share."
    )
    p_create_share.add_argument(
        "--owner",
        default="root",
        help="The user who will own the files (default: root).",
    )
    p_create_share.add_argument(
        "--group",
        default="smb_users",
        help="The group that will own the files (default: smb_users).",
    )
    p_create_share.add_argument(
        "--perms",
        default="775",
        help="File system permissions for the share's root (default: 775).",
    )
    p_create_share.add_argument(
        "--valid-users",
        help="Comma-separated list of users/groups allowed to connect. Use '@' for groups.",
    )
    p_create_share.add_argument(
        "--readonly",
        action="store_true",
        help="Make the share read-only (default: no).",
    )
    p_create_share.add_argument(
        "--no-browse",
        action="store_true",
        help="Hide the share from network Browse (default: browseable).",
    )
    p_create_share.add_argument(
        "--quota", help="Set a ZFS quota for the share (e.g., 100G)."
    )
    p_create_share.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
    )
    p_create_share.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_create_share.set_defaults(func=cmd_create_share)

    p_create_group = create_sub.add_parser("group", help="Create a new group.")
    p_create_group.add_argument("group", help="The name of the group.")
    p_create_group.add_argument(
        "--description", default="", help="A description for the group."
    )
    p_create_group.add_argument(
        "--users", help="A comma-separated list of initial members."
    )
    p_create_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
    )
    p_create_group.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_create_group.set_defaults(func=cmd_create_group)
    
    # --- Modify Parser ---
    p_modify = subparsers.add_parser(
        "modify", help="Modify an existing user, share, or group.")
    modify_sub = p_modify.add_subparsers(dest="modify_type", required=True)
    p_modify_group = modify_sub.add_parser(
        "group", help="Modify a group's membership.")
    p_modify_group.add_argument(
        "group", help="The name of the group to modify.")
    p_modify_group.add_argument(
        "--add-users", help="Comma-separated list of users to add.")
    p_modify_group.add_argument(
        "--remove-users", help="Comma-separated list of users to remove.")
    p_modify_group.add_argument('--dry-run', action='store_true',
                                help="Don't change anything just summarize the changes")
    p_modify_group.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_modify_group.set_defaults(func=cmd_modify_group)

    p_modify_share = modify_sub.add_parser(
        "share", help="Modify a share's properties.")
    p_modify_share.add_argument(
        "share", help="The name of the share to modify.")
    p_modify_share.add_argument(
        "--name", help="Rename the share and dataset.")
    p_modify_share.add_argument(
        "--pool", help="Move the share's dataset to a new ZFS pool.")
    p_modify_share.add_argument(
        "--comment", help="New description for the share.")
    p_modify_share.add_argument(
        "--owner", help="New user who will own the files.")
    p_modify_share.add_argument(
        "--group", help="New group that will own the files.")
    p_modify_share.add_argument(
        "--perms", help="New file system permissions (e.g., 770).")
    p_modify_share.add_argument(
        "--valid-users", help="New list of allowed users/groups.")
    p_modify_share.add_argument(
        "--readonly", action=argparse.BooleanOptionalAction, help="Set the share as read-only.")
    p_modify_share.add_argument(
        "--no-browse", action=argparse.BooleanOptionalAction, help="Hide the share from network Browse.")
    p_modify_share.add_argument(
        "--quota", help="New ZFS quota for the share (e.g., 200G). Use 'none' to remove.")
    p_modify_share.add_argument('--dry-run', action='store_true',
                                help="Don't change anything just summarize the changes")
    p_modify_share.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_modify_share.set_defaults(func=cmd_modify_share)

    p_modify_setup = modify_sub.add_parser(
        "setup", help="Modify global server configuration.")
    p_modify_setup.add_argument(
        "--primary-pool", help="New primary pool.")
    p_modify_setup.add_argument(
        "--add-secondary-pools", nargs='*', help="Add new pools for shares.")
    p_modify_setup.add_argument(
        "--remove-secondary-pools", nargs='*', help="Remove secondary pools.")
    p_modify_setup.add_argument(
        "--server-name", help="New server NetBIOS name.")
    p_modify_setup.add_argument("--workgroup", help="New workgroup name.")
    p_modify_setup.add_argument(
        "--macos", action=argparse.BooleanOptionalAction, help="Enable or disable macOS optimizations.")
    p_modify_setup.add_argument(
        "--default-home-quota", help="New default quota for user homes (e.g., 50G). Use 'none' to remove.")
    p_modify_setup.add_argument('--dry-run', action='store_true',
                                help="Don't change anything just summarize the changes")
    p_modify_setup.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_modify_setup.set_defaults(func=cmd_modify_setup)

    p_modify_home = modify_sub.add_parser(
        "home", help="Modify a user's home quota.")
    p_modify_home.add_argument("user", help="The user to modify.")
    p_modify_home.add_argument(
        "--quota", required=True, help="The new quota for the home directory (e.g., 20G). Use 'none' to remove.")
    p_modify_home.add_argument('--dry-run', action='store_true',
                               help="Don't change anything just summarize the changes")
    p_modify_home.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_modify_home.set_defaults(func=cmd_modify_home)
    
    # --- Delete Parser ---
    p_delete = subparsers.add_parser(
        "delete", help="Delete a user, share, or group.")
    delete_sub = p_delete.add_subparsers(dest="delete_type", required=True)
    p_delete_user = delete_sub.add_parser("user", help="Delete a user.")
    p_delete_user.add_argument("user", help="The username to delete.")
    p_delete_user.add_argument(
        "--delete-data",
        action="store_true",
        help="Permanently delete the associated ZFS dataset.",
    )
    p_delete_user.add_argument(
        "--yes",
        action="store_true",
        help="Assume 'yes' to destructive confirmation prompts.",
    )
    p_delete_user.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
    )
    p_delete_user.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_delete_user.set_defaults(func=cmd_delete_user)

    p_delete_share = delete_sub.add_parser("share", help="Delete a share.")
    p_delete_share.add_argument("share", help="The share name to delete.")
    p_delete_share.add_argument(
        "--delete-data",
        action="store_true",
        help="Permanently delete the associated ZFS dataset.",
    )
    p_delete_share.add_argument(
        "--yes",
        action="store_true",
        help="Assume 'yes' to destructive confirmation prompts.",
    )
    p_delete_share.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
    )
    p_delete_share.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_delete_share.set_defaults(func=cmd_delete_share)

    p_delete_group = delete_sub.add_parser("group", help="Delete a group.")
    p_delete_group.add_argument("group", help="The group name to delete.")
    p_delete_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
    )
    p_delete_group.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_delete_group.set_defaults(func=cmd_delete_group)
    
    # --- Other Parsers ---
    p_list = subparsers.add_parser(
        "list", help="List all managed users, shares, groups or pools.")
    p_list.add_argument(
        "type", choices=["users", "shares", "groups", "pools"], help="The type of item to list."
    )
    p_list.set_defaults(func=cmd_list)

    p_passwd = subparsers.add_parser(
        "passwd", help="Change a user's Samba password.")
    p_passwd.add_argument("user", help="The user whose password to change.")
    p_passwd.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_passwd.set_defaults(func=cmd_passwd)

    p_remove = subparsers.add_parser(
        "remove", help="Uninstall smb-zfs and remove all related configurations and data."
    )
    p_remove.add_argument(
        "--delete-data",
        action="store_true",
        help="Permanently delete all associated ZFS datasets.",
    )
    p_remove.add_argument(
        "--delete-users",
        action="store_true",
        help="Permanently delete all users and groups created by this tool.",
    )
    p_remove.add_argument(
        "--yes",
        action="store_true",
        help="Assume 'yes' to destructive confirmation prompts.",
    )
    p_remove.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
    )
    p_remove.add_argument(
        "--json", action="store_true", help="Output result as a JSON object."
    )
    p_remove.set_defaults(func=cmd_remove)

    p_get_state = subparsers.add_parser(
        "get-state", help="Print the current state as JSON."
    )
    p_get_state.set_defaults(func=cmd_get_state)
    
    return parser

def main() -> None:
    """The main entry point for the CLI application."""
    parser = create_parser()
    args = parser.parse_args()

    # --- Setup Logging ---
    log_level = logging.ERROR
    if args.verbose == 1:
        log_level = logging.WARNING
    elif args.verbose == 2:
        log_level = logging.INFO
    elif args.verbose >= 3:
        log_level = logging.DEBUG

    log.setLevel(log_level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    try:
        log.debug("Initializing SmbZfsManager.")
        manager = SmbZfsManager()
        log.debug("Executing command: %s", args.command)
        args.func(manager, args)
        log.debug("Command %s finished successfully.", args.command)
    except SmbZfsError as e:
        log.error("A known error occurred: %s", e,
                  exc_info=(log_level <= logging.DEBUG))
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        log.critical("An unexpected error occurred: %s", e, exc_info=True)
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
