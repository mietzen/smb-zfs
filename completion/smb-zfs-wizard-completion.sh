#!/bin/bash

# Bash completion script for smb-zfs-wizard
#
# To install:
# 1. Place this file in your bash completion directory.
#    - For system-wide access: /etc/bash_completion.d/
#    - For user-specific access: ~/.local/share/bash-completion/completions/
# 2. Source the file or restart your shell:
#    source /path/to/this/script/smb-zfs-wizard-completion.sh

_smb_zfs_wizard_completion() {
    local cur prev words cword
    _get_comp_words_by_ref -n : cur prev words cword

    # Define all possible commands and sub-commands.
    local commands="setup create modify delete remove"
    local create_opts="user share group"
    local modify_opts="group share setup"
    local delete_opts="user share group"
    local global_opts="-h --help -v --version"

    # Completion for the first argument (the main command).
    if [ "$cword" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "${commands} ${global_opts}" -- "${cur}") )
        return 0
    fi

    local command="${words[1]}"
    case "${command}" in
        create)
            # Complete the sub-command (user, share, group)
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "${create_opts}" -- "${cur}") )
            fi
            ;;
        modify)
            # Complete the sub-command (group, share, setup)
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "${modify_opts}" -- "${cur}") )
            fi
            ;;
        delete)
            # Complete the sub-command (user, share, group)
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "${delete_opts}" -- "${cur}") )
            fi
            ;;
    esac

    return 0
}

# Register the completion function for the 'smb-zfs-wizard' command.
complete -F _smb_zfs_wizard_completion smb-zfs-wizard
