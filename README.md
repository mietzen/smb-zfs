# Samba & ZFS Management Tool

A command-line tool for simplifying Samba share management on ZFS-backed systems.

`smb-zfs` automates the setup and administration of users, groups, and shares, ensuring Samba and ZFS configurations remain synchronized.

It provides a reliable interface for common administrative tasks through two modes: a standard CLI `smb-zfs` for scripting and an interactive wizard `smb-zfs-wizard` for guided setup.

```text
$ smb-zfs -h
usage: smb-zfs [-h] [-v] {install,create,delete,list,passwd,uninstall} ...

A tool to manage Samba on a ZFS-backed system.

positional arguments:
  {install,create,delete,list,passwd,uninstall}
                        Available commands
    install             Initial setup of Samba, ZFS, and Avahi.
    create              Create a new user, share, or group.
    delete              Remove a user, share, or group.
    list                List all items of a specific type.
    passwd              Change a user's password.
    uninstall           Remove all configurations, data, and packages.

options:
  -h, --help            show this help message and exit
  -v, --version         show program's version number and exit
```

 ## Prerequisites

- Debian 12 - Bookworm
- ZFS installed with a pre-existing pool
- Python 3.11
- `sudo` privileges

## Installation

Install package:

```Shell
sudo apt update
sudo apt install -y pipx samba avahi-daemon
sudo PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install smb-zfs
echo PIPX_HOME=/opt/pipx >> ~/.bashrc
echo PIPX_BIN_DIR=/usr/local/bin >> ~/.bashrc
```

Install `bash` completion:

```Shell
wget "https://raw.githubusercontent.com/mietzen/smb-zfs/refs/tags/$(smb-zfs -v)/completion/smb-zfs-wizard-completion.sh" -O /etc/bash_completion.d/smb-zfs-wizard-completion.sh
wget "https://raw.githubusercontent.com/mietzen/smb-zfs/refs/tags/$(smb-zfs -v)/completion/smb-zfs-completion.sh" -O /etc/bash_completion.d/smb-zfs-completion.sh
```

This makes the `smb-zfs` and `smb-zfs-wizard` commands available system-wide.

## Quick Start: Use the Wizard for Guided Setup

```Shell
$ smb-zfs --help
usage: smb-zfs [-h] [-v] {setup,create,modify,delete,list,passwd,remove} ...

A tool to manage Samba on a ZFS-backed system.

positional arguments:
  {setup,create,modify,delete,list,passwd,remove}
                        Available commands
    setup               Initial setup of Samba, ZFS, and Avahi.
    create              Create a new user, share, or group.
    modify              Modify an existing user, share, or group.
    delete              Remove a user, share, or group.
    list                List all items of a specific type.
    passwd              Change a user's password.
    remove              Remove all configurations and data.

options:
  -h, --help            show this help message and exit
  -v, --version         show program's version number and exit
```

Example setup:


```Shell
$ smb-zfs-wizard setup

--- Initial System Setup Wizard ---
Available ZFS pools: data, rpool, tank
Enter the name of the ZFS pool to use: tank
Enter the server's NetBIOS name [nas]:
Enter the workgroup name [WORKGROUP]:
Enable macOS compatibility optimizations? [y/N]  [n]: y

Summary of actions:
 - ZFS Pool: tank
 - Server Name: nas
 - Workgroup: WORKGROUP
 - macOS Optimized: True
Proceed with setup? [Y/n]  [y]:

Success: Setup completed successfully.
```

```Shell
$ smb-zfs-wizard create user

--- Create New User Wizard ---
Enter the new username: nils
Enter password for user 'nils':
Confirm password:
Allow shell access (/bin/bash)? [y/N]  [n]: y
Available groups: smb_users
Enter comma-separated groups to add user to (optional): smb_users

Success: User 'nils' created successfully.
```

```Shell
$ smb-zfs-wizard create share

--- Create New Share Wizard ---
Enter the name for the new share: media
Enter the ZFS dataset path within the pool (e.g., data/media): media
Enter a comment for the share (optional): Movies, Series, Music, etc.
Available users: nils
Enter the owner for the share's files (default: root):
Available groups: smb_users
Enter the group for the share's files (default: smb_users):
Enter file system permissions for the share root [0775]:
Enter valid users/groups (e.g., @smb_users) [@smb_users]:
Make the share read-only? [y/N]  [n]:
Make the share browseable? [Y/n]  [y]:

Success: Share 'media' created successfully.
```

## Advanced CLI usage

All commands must be run with root privileges.

Initial Setup:

```Shell
sudo smb-zfs install --pool <your-zfs-pool>
```

Create a User:

```Shell
sudo smb-zfs create user john --shell
```

Create a Share:

```Shell
# Creates the dataset 'your-zfs-pool/data/media'
sudo smb-zfs create share media --dataset data/media
```

## Update `smb-zfs`

```Shell
pipx upgrade smb-zfs
```

## Uninstallation

```Shell
sudo smb-zfs-wizard remove
sudo pipx remove smb-zfs

# Remove apt pkgs
sudo apt remove pipx samba samba-common-bin avahi-daemon
```
