#!/usr/bin/env python3

import argparse
import getpass
import sys
import socket
import os

from importlib import metadata
from . import SmbZfsManager, SmbZfsError

PROG_NAME = "smb-zfs"
CONFIRM_PHRASE = "I KNOW WHAT I AM DOING"


def handle_exception(func):
    """Decorator to catch and print SmbZfsError exceptions."""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SmbZfsError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    return wrapper


def confirm_destructive_action(prompt, yes_flag):
    """Ask for confirmation for a destructive action."""
    if yes_flag:
        return True
    print(f"WARNING: {prompt}", file=sys.stderr)
    print(
        f"To proceed, type the following phrase exactly: {CONFIRM_PHRASE}",
        file=sys.stderr,
    )
    response = input("> ")
    return response == CONFIRM_PHRASE


def check_root():
    if os.geteuid() != 0:
        raise SmbZfsError("This script must be run as root.")


@handle_exception
def cmd_install(manager, args):
    """Handler for the 'install' command."""
    check_root()
    server_name = args.server_name or socket.gethostname()
    workgroup = args.workgroup or "WORKGROUP"

    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print("  - Install packages: samba, samba-common-bin, avahi-daemon")
        print(f"  - Create ZFS dataset: {args.pool}/homes")
        print("  - Create system group: smb_users")
        print(f"  - Generate {manager._config.SMB_CONF} with:")
        print(f"    - Pool: {args.pool}")
        print(f"    - Server Name: {server_name}")
        print(f"    - Workgroup: {workgroup}")
        print(f"    - macOS optimized: {args.macos}")
        print(f"  - Generate {manager._config.AVAHI_SMB_SERVICE}")
        print("  - Enable and start smbd, nmbd, avahi-daemon services")
        print(f"  - Initialize state file at {manager._state.path}")
        return

    result = manager.install(args.pool, server_name, workgroup, args.macos)
    print(result)


@handle_exception
def cmd_create_user(manager, args):
    """Handler for the 'create user' command."""
    password = args.password or getpass.getpass(
        f"Enter password for user '{args.user}': "
    )
    groups = args.groups.split(",") if args.groups else []

    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print(f"  - Create system user: {args.user}")
        print(
            f"  - Create ZFS home dataset: {manager._state.get('zfs_pool')}/homes/{args.user}"
        )
        print("  - Set permissions on home directory")
        print(f"  - Add Samba user: {args.user}")
        print("  - Add user to group 'smb_users'")
        if groups:
            print(f"  - Add user to additional groups: {', '.join(groups)}")
        print("  - Update state file")
        return

    check_root()
    result = manager.create_user(args.user, password, args.shell, groups)
    print(result)


@handle_exception
def cmd_create_share(manager, args):
    """Handler for the 'create share' command."""
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print(
            f"  - Create ZFS dataset: {manager._state.get('zfs_pool')}/{args.dataset}"
        )
        print(
            f"  - Set ownership to {args.owner}:{args.group} and permissions to {args.perms}"
        )
        print(f"  - Add share '{args.share}' to {manager._config.SMB_CONF}")
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
    )
    print(result)


@handle_exception
def cmd_create_group(manager, args):
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
    print(result)


@handle_exception
def cmd_delete_user(manager, args):
    """Handler for the 'delete user' command."""
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print(f"  - Remove Samba user: {args.user}")
        print(f"  - Remove system user: {args.user}")
        if args.delete_data:
            print(
                f"  - DESTROY ZFS dataset: {manager._state.get_item('users', args.user)['home_dataset']}"
            )
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
    print(result)


@handle_exception
def cmd_delete_share(manager, args):
    """Handler for the 'delete share' command."""
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print(f"  - Remove share '{args.share}' from {manager._config.SMB_CONF}")
        if args.delete_data:
            print(
                f"  - DESTROY ZFS dataset: {manager._state.get_item('shares', args.share)['dataset']}"
            )
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
    print(result)


@handle_exception
def cmd_delete_group(manager, args):
    """Handler for the 'delete group' command."""
    if args.dry_run:
        print("--- Dry Run ---")
        print("Would perform the following actions:")
        print(f"  - Remove system group: {args.group}")
        print("  - Update state file")
        return

    check_root()
    result = manager.delete_group(args.group)
    print(result)


@handle_exception
def cmd_list(manager, args):
    """Handler for the 'list' command."""
    items = manager.list_items(args.type)
    if not items:
        print(f"No {args.type} found.")
        return

    for name, data in items.items():
        print(f"--- {name} ---")
        for key, value in data.items():
            if isinstance(value, list):
                value = ", ".join(value) if value else "None"
            print(f"  {key.replace('_', ' ').capitalize()}: {value}")
        print()


@handle_exception
def cmd_passwd(manager, args):
    """Handler for the 'passwd' command."""
    password = getpass.getpass(f"Enter new password for user '{args.user}': ")
    password_confirm = getpass.getpass("Confirm new password: ")
    if password != password_confirm:
        print("Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    if getpass.getuser() != args.user:
        check_root()
    result = manager.change_password(args.user, password)
    print(result)


@handle_exception
def cmd_uninstall(manager, args):
    """Handler for the 'uninstall' command."""
    prompt = "This will remove all configurations, packages, and potentially all user data and users created by this tool."
    if not confirm_destructive_action(prompt, args.yes):
        print("Operation cancelled.", file=sys.stderr)
        return

    check_root()
    result = manager.uninstall(args.delete_data, args.delete_users)
    print(result)


def main():
    parser = argparse.ArgumentParser(
        prog=PROG_NAME,
        description="A tool to manage Samba on a ZFS-backed system.",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"{metadata.version('smb-zfs')}"
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Available commands"
    )

    # --- Install ---
    p_install = subparsers.add_parser(
        "install", help="Initial setup of Samba, ZFS, and Avahi."
    )
    p_install.add_argument(
        "--pool", required=True, help="The name of the ZFS pool to use."
    )
    p_install.add_argument(
        "--server-name", help="The server's NetBIOS name (default: hostname)."
    )
    p_install.add_argument(
        "--workgroup", help="The workgroup name (default: WORKGROUP)."
    )
    p_install.add_argument(
        "--macos", action="store_true", help="Enable macOS compatibility optimizations."
    )
    p_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
    )
    p_install.set_defaults(func=cmd_install)

    # --- Create ---
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
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
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
        help="Hide the share from network browsing (default: browseable).",
    )
    p_create_share.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
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
    p_create_group.set_defaults(func=cmd_create_group)

    # --- Delete ---
    p_delete = subparsers.add_parser("delete", help="Remove a user, share, or group.")
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
    p_delete_share.set_defaults(func=cmd_delete_share)

    p_delete_group = delete_sub.add_parser("group", help="Delete a group.")
    p_delete_group.add_argument("group", help="The group name to delete.")
    p_delete_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't change anything just summarize the changes",
    )
    p_delete_group.set_defaults(func=cmd_delete_group)

    # --- List ---
    p_list = subparsers.add_parser("list", help="List all items of a specific type.")
    p_list.add_argument(
        "type", choices=["users", "shares", "groups"], help="The type of item to list."
    )
    p_list.set_defaults(func=cmd_list)

    # --- Passwd ---
    p_passwd = subparsers.add_parser("passwd", help="Change a user's password.")
    p_passwd.add_argument("user", help="The user whose password to change.")
    p_passwd.set_defaults(func=cmd_passwd)

    # --- Uninstall ---
    p_uninstall = subparsers.add_parser(
        "uninstall", help="Remove all configurations, data, and packages."
    )
    p_uninstall.add_argument(
        "--delete-data",
        action="store_true",
        help="Permanently delete all associated ZFS datasets.",
    )
    p_uninstall.add_argument(
        "--delete-users",
        action="store_true",
        help="Permanently delete all users and groups created by this tool.",
    )
    p_uninstall.add_argument(
        "--yes",
        action="store_true",
        help="Assume 'yes' to destructive confirmation prompts.",
    )
    p_uninstall.set_defaults(func=cmd_uninstall)

    args = parser.parse_args()

    try:
        manager = SmbZfsManager()
        args.func(manager, args)
    except SmbZfsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
