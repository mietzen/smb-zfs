# Samba & ZFS Management Tool

A command-line tool for simplifying Samba share management on ZFS-backed systems.

`smb-zfs` automates the setup and administration of users, groups, and shares, ensuring Samba and ZFS configurations remain synchronized.

It provides a reliable interface for common administrative tasks through two modes: a standard CLI `smb-zfs` for scripting and an interactive wizard `smb-zfs-wizard` for guided setup.

 ## Prerequisites

- A Debian-based Linux distribution.
- ZFS installed with a pre-existing pool.
- Root or sudo privileges.

## Installation

Install the package

    sudo apt update
    sudo apt install pipx
    sudo pipx ensurepath --global
    sudo pipx install git+https://github.com/mietzen/smb-zfs.git

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
