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

Install package

```Shell
sudo apt update
sudo apt install -y pipx samba samba-common-bin avahi-daemon
sudo PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install smb-zfs
```

This makes the `smb-zfs` and `smb-zfs-wizard` commands available system-wide.

## Quick Start

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

## Use the Wizard for Guided Setup

```Shell
sudo smb-zfs-wizard install
sudo smb-zfs-wizard create user
```

For a full list of commands, use the `--help` flag with any command.

## Uninstallation

Install the package

```Shell
sudo smb-zfs-wizard remove
sudo pipx remove smb-zfs

# Remove apt pkgs
sudo apt remove pipx samba samba-common-bin avahi-daemon
```
