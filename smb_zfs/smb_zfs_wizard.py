#!/usr/bin/env python3

import argparse
import getpass
import sys
import socket
from importlib import metadata
from . import SmbZfsManager, SmbZfsError

CONFIRM_PHRASE = "I KNOW WHAT I AM DOING"

# --- Helper functions for user input ---


def prompt(message, default=None):
    """General purpose prompt for a string value."""
    if default:
        return input(f"{message} [{default}]: ") or default
    return input(f"{message}: ")


def prompt_yes_no(message, default="n"):
    """Prompts for a yes/no answer."""
    options = "[y/N]" if default.lower() == "n" else "[Y/n]"
    while True:
        response = input(f"{message} {options} ").lower() or default
        if response in ["y", "yes"]:
            return True
        if response in ["n", "no"]:
            return False
        print("Please answer 'yes' or 'no'.")


def prompt_for_password(username):
    """Securely prompts for a password and confirmation."""
    while True:
        password = getpass.getpass(f"Enter password for user '{username}': ")
        if not password:
            print("Password cannot be empty.", file=sys.stderr)
            continue
        password_confirm = getpass.getpass("Confirm password: ")
        if password == password_confirm:
            return password
        print("Passwords do not match. Please try again.", file=sys.stderr)


def confirm_destructive_action(message):
    """Asks for confirmation before performing a destructive action."""
    print(f"\n!!! WARNING !!!\n{message}", file=sys.stderr)
    print(
        f"To proceed, you must type the following phrase exactly: {CONFIRM_PHRASE}",
        file=sys.stderr,
    )
    response = input("> ")
    if response == CONFIRM_PHRASE:
        print("Confirmation received.")
        return True
    print("Confirmation failed. Operation cancelled.", file=sys.stderr)
    return False


# --- Wizard functions for each command ---


def wizard_install(manager, args=None):
    print("\n--- Initial System Setup Wizard ---")
    try:
        pool = prompt("Enter the name of the ZFS pool to use")
        if not pool:
            raise ValueError("Pool name cannot be empty.")
        server_name = prompt(
            "Enter the server's NetBIOS name", default=socket.gethostname()
        )
        workgroup = prompt("Enter the workgroup name", default="WORKGROUP")
        macos_optimized = prompt_yes_no(
            "Enable macOS compatibility optimizations?", default="n"
        )

        print("\nSummary of actions:")
        print(f" - ZFS Pool: {pool}")
        print(f" - Server Name: {server_name}")
        print(f" - Workgroup: {workgroup}")
        print(f" - macOS Optimized: {macos_optimized}")

        if prompt_yes_no("Proceed with installation?", default="y"):
            result = manager.install(pool, server_name, workgroup, macos_optimized)
            print(f"\nSuccess: {result}")
    except (SmbZfsError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)


def wizard_create_user(manager, args=None):
    print("\n--- Create New User Wizard ---")
    try:
        username = prompt("Enter the new username")
        if not username:
            raise ValueError("Username cannot be empty.")

        password = prompt_for_password(username)
        allow_shell = prompt_yes_no("Allow shell access (/bin/bash)?", default="n")

        groups_str = prompt("Enter comma-separated groups to add user to (optional)")
        groups = [g.strip() for g in groups_str.split(",")] if groups_str else []

        result = manager.create_user(username, password, allow_shell, groups)
        print(f"\nSuccess: {result}")
    except (SmbZfsError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)


def wizard_create_share(manager, args=None):
    print("\n--- Create New Share Wizard ---")
    try:
        share_name = prompt("Enter the name for the new share")
        if not share_name:
            raise ValueError("Share name cannot be empty.")
        dataset_path = prompt(
            "Enter the ZFS dataset path within the pool (e.g., data/media)"
        )
        if not dataset_path:
            raise ValueError("Dataset path cannot be empty.")

        comment = prompt("Enter a comment for the share (optional)")
        owner = prompt("Enter the owner for the share's files", default="root")
        group = prompt("Enter the group for the share's files", default="smb_users")
        perms = prompt(
            "Enter file system permissions for the share root", default="0775"
        )
        valid_users = prompt(
            "Enter valid users/groups (e.g., @smb_users)", default=f"@{group}"
        )
        read_only = prompt_yes_no("Make the share read-only?", default="n")
        browseable = prompt_yes_no("Make the share browseable?", default="y")

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
        )
        print(f"\nSuccess: {result}")

    except (SmbZfsError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)


def wizard_create_group(manager, args=None):
    print("\n--- Create New Group Wizard ---")
    try:
        group_name = prompt("Enter the name for the new group")
        if not group_name:
            raise ValueError("Group name cannot be empty.")

        description = prompt("Enter a description for the group (optional)")
        users_str = prompt("Enter comma-separated initial members (optional)")
        users = [u.strip() for u in users_str.split(",")] if users_str else []

        result = manager.create_group(group_name, description, users)
        print(f"\nSuccess: {result}")

    except (SmbZfsError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)


def wizard_delete_user(manager, args=None):
    print("\n--- Delete User Wizard ---")
    try:
        username = prompt("Enter the username to delete")
        if not username:
            return

        delete_data = prompt_yes_no(
            f"Delete user '{username}'s home directory and all its data?", default="n"
        )

        if delete_data:
            if not confirm_destructive_action(
                f"This will PERMANENTLY delete user '{username}' AND their home directory."
            ):
                return

        result = manager.delete_user(username, delete_data)
        print(f"\nSuccess: {result}")
    except SmbZfsError as e:
        print(f"\nError: {e}", file=sys.stderr)


def wizard_delete_share(manager, args=None):
    print("\n--- Delete Share Wizard ---")
    try:
        share_name = prompt("Enter the name of the share to delete")
        if not share_name:
            return

        delete_data = prompt_yes_no(
            f"Delete the ZFS dataset for share '{share_name}' and all its data?",
            default="n",
        )

        if delete_data:
            if not confirm_destructive_action(
                f"This will PERMANENTLY delete the ZFS dataset for share '{share_name}'."
            ):
                return

        result = manager.delete_share(share_name, delete_data)
        print(f"\nSuccess: {result}")
    except SmbZfsError as e:
        print(f"\nError: {e}", file=sys.stderr)


def wizard_delete_group(manager, args=None):
    print("\n--- Delete Group Wizard ---")
    try:
        group_name = prompt("Enter the name of the group to delete")
        if not group_name:
            return

        result = manager.delete_group(group_name)
        print(f"\nSuccess: {result}")
    except SmbZfsError as e:
        print(f"\nError: {e}", file=sys.stderr)


def wizard_uninstall(manager, args=None):
    print("\n--- Uninstall Wizard ---")
    try:
        delete_data = prompt_yes_no(
            "Delete ALL ZFS datasets created by this tool (user homes, shares)?",
            default="n",
        )
        delete_users = prompt_yes_no(
            "Delete ALL users and groups created by this tool?", default="n"
        )

        message = "This will remove all configurations, packages, and potentially all user data and users created by this tool."
        if confirm_destructive_action(message):
            result = manager.uninstall(delete_data, delete_users)
            print(f"\nSuccess: {result}")
    except SmbZfsError as e:
        print(f"\nError: {e}", file=sys.stderr)


def main():
    """Main function to run the wizard."""
    parser = argparse.ArgumentParser(
        prog="smb-zfs-wizard",
        description="An interactive wizard to manage Samba on a ZFS-backed system.",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"{metadata.version('smb-zfs')}"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    # If no command is given, print help and exit.
    subparsers.required = True

    # --- Define parsers for each command ---
    p_install = subparsers.add_parser("install", help="Start the initial setup wizard.")
    p_install.set_defaults(func=wizard_install)

    p_create = subparsers.add_parser("create", help="Start a creation wizard.")
    create_sub = p_create.add_subparsers(dest="create_type", required=True)
    p_create_user = create_sub.add_parser("user", help="Start the new user wizard.")
    p_create_user.set_defaults(func=wizard_create_user)
    p_create_share = create_sub.add_parser("share", help="Start the new share wizard.")
    p_create_share.set_defaults(func=wizard_create_share)
    p_create_group = create_sub.add_parser("group", help="Start the new group wizard.")
    p_create_group.set_defaults(func=wizard_create_group)

    p_delete = subparsers.add_parser("delete", help="Start a deletion wizard.")
    delete_sub = p_delete.add_subparsers(dest="delete_type", required=True)
    p_delete_user = delete_sub.add_parser("user", help="Start the delete user wizard.")
    p_delete_user.set_defaults(func=wizard_delete_user)
    p_delete_share = delete_sub.add_parser(
        "share", help="Start the delete share wizard."
    )
    p_delete_share.set_defaults(func=wizard_delete_share)
    p_delete_group = delete_sub.add_parser(
        "group", help="Start the delete group wizard."
    )
    p_delete_group.set_defaults(func=wizard_delete_group)

    p_uninstall = subparsers.add_parser(
        "uninstall", help="Start the uninstallation wizard."
    )
    p_uninstall.set_defaults(func=wizard_uninstall)

    args = parser.parse_args()

    try:
        manager = SmbZfsManager()
        # Call the function associated with the chosen command
        args.func(manager, args)
    except SmbZfsError as e:
        print(f"Initialization Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
