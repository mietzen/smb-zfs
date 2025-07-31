#!/bin/bash

# Bash completion script for smb-zfs
#
# To install:
# 1. Place this file in your bash completion directory.
#    - For system-wide access: /etc/bash_completion.d/
#    - For user-specific access: ~/.local/share/bash-completion/completions/
# 2. Source the file or restart your shell:
#    source /path/to/this/script/smb-zfs-completion.sh

# Helper function to get a list of managed items (users, shares, groups)
# by calling the smb-zfs list command and parsing its output.
_get_managed_items() {
    local type="$1"
    # The list command outputs "--- item_name ---". This pipeline extracts the name.
    # Errors are redirected to /dev/null in case the system is not yet initialized.
    smb-zfs list "$type" 2>/dev/null | grep -- '---' | sed -e 's/--- //g' -e 's/ ---//g'
}

_smb_zfs_completion() {
    # COMP_WORDS: An array containing the individual words in the current command line.
    # COMP_CWORD: The index of the word containing the current cursor position.
    # cur: The current word being completed.
    local cur prev words cword
    _get_comp_words_by_ref -n : cur prev words cword

    # Define all possible commands, sub-commands, and global options.
    local commands="setup create modify list delete passwd remove get-state wizard"
    local create_opts="user share group"
    local modify_opts="group share setup home"
    local delete_opts="user share group"
    local list_opts="users shares groups pools"
    local wizard_opts="setup create modify delete remove"
    local global_opts="-h --help --version --verbose"

    # Completion for the first argument (the main command).
    if [ "$cword" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "${commands} ${global_opts}" -- "${cur}") )
        return 0
    fi

    local command="${words[1]}"
    case "${command}" in
        setup)
            local opts="--primary-pool --secondary-pools --server-name --workgroup --macos --default-home-quota --dry-run --json --verbose"
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            ;;
        create)
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "${create_opts}" -- "${cur}") )
                return 0
            fi
            local sub_command="${words[2]}"
            local opts=""
            case "${sub_command}" in
                user)
                    opts="--password --shell --groups --no-home --dry-run --json --verbose"
                    ;;
                share)
                    opts="--dataset --pool --comment --owner --group --perms --valid-users --readonly --no-browse --quota --dry-run --json --verbose"
                    ;;
                group)
                    opts="--description --users --dry-run --json --verbose"
                    ;;
            esac
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            ;;
        modify)
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "${modify_opts}" -- "${cur}") )
                return 0
            fi
            local sub_command="${words[2]}"
            local opts=""
            case "${sub_command}" in
                group|share|home)
                    if [ "$cword" -eq 3 ]; then
                        local item_type="users" # for home
                        if [ "${sub_command}" != "home" ]; then
                            item_type="${sub_command}s"
                        fi
                        COMPREPLY=( $(compgen -W "$(_get_managed_items ${item_type})" -- "${cur}") )
                        return 0
                    fi
                    if [ "${sub_command}" == "group" ]; then
                        opts="--add-users --remove-users --dry-run --json --verbose"
                    elif [ "${sub_command}" == "share" ]; then
                        opts="--name --pool --comment --valid-users --readonly --no-readonly --no-browse --browse --perms --owner --group --quota --dry-run --json --verbose"
                    elif [ "${sub_command}" == "home" ]; then
                        opts="--quota --dry-run --json --verbose"
                    fi
                    ;;
                setup)
                    opts="--primary-pool --add-secondary-pools --remove-secondary-pools --server-name --workgroup --macos --no-macos --default-home-quota --dry-run --json --verbose"
                    ;;
            esac
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            ;;
        list)
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "${list_opts}" -- "${cur}") )
            fi
            ;;
        delete)
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "${delete_opts}" -- "${cur}") )
                return 0
            fi
            local sub_command="${words[2]}"
            if [ "$cword" -eq 3 ]; then
                COMPREPLY=( $(compgen -W "$(_get_managed_items ${sub_command}s)" -- "${cur}") )
                return 0
            fi
            local opts="--delete-data --yes --dry-run --json --verbose"
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            ;;
        passwd)
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "$(_get_managed_items users)" -- "${cur}") )
                return 0
            fi
            if [ "$cword" -eq 3 ]; then
                local opts="--json --verbose"
                COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            fi
            ;;
        remove)
            local opts="--delete-data --delete-users --yes --dry-run --json --verbose"
            COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
            ;;
        wizard)
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "${wizard_opts}" -- "${cur}") )
                return 0
            fi
            local wizard_sub_command="${words[2]}"
            case "${wizard_sub_command}" in
                create)
                    COMPREPLY=( $(compgen -W "${create_opts}" -- "${cur}") )
                    ;;
                modify)
                    COMPREPLY=( $(compgen -W "${modify_opts}" -- "${cur}") )
                    ;;
                delete)
                    COMPREPLY=( $(compgen -W "${delete_opts}" -- "${cur}") )
                    ;;
                *)
                    # No further completions after a wizard command is selected
                    COMPREPLY=()
                    ;;
            esac
            ;;
        get-state)
            # No options for get-state
            COMPREPLY=()
            ;;
    esac

    return 0
}

# Register the completion function for the 'smb-zfs' command.
complete -F _smb_zfs_completion smb-zfs
