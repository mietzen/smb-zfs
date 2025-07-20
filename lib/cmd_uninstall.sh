# Uninstall
# TODO: Add --delete-data option to delete zfs dataset, don't delete data by default, give a more alarming note
# TODO: Add --delete-users option to delete users & groups, don't delete users & groups by default, give a more alarming note
# TODO: Use read -r -p

cmd_uninstall() {
    check_initialized

    print_info "Removing all configuration"
    print_warning "This will remove:"
    echo "  - All Samba configuration"
    echo "  - All Avahi configuration"
    echo "  - All users created by this tool"
    echo "  - All groups created by this tool"
    echo "  - All ZFS datasets (HOME DIRECTORIES AND SHARES)"
    echo "  - State file"
    echo ""
    print_error "THIS WILL DELETE ALL USER DATA!"
    echo ""

    echo "Are you absolutely sure? Type 'UNINSTALL' to confirm:"
    read -r confirm
    if [[ "$confirm" != "UNINSTALL" ]]; then
        echo "Uninstallation cancelled."
        exit 0
    fi

    local pool
    pool=$(get_state_value "zfs_pool" "")
    local state
    state=$(read_state)

    # Remove all users
    print_info "Removing users..."
    echo "$state" | jq -r '.users | keys[]' | while read -r username; do
        print_info "Removing user: $username"

        # Remove from Samba
        if pdbedit -L | grep -q "^$username:"; then
            smbpasswd -x "$username" 2>/dev/null || true
        fi

        # Remove system user
        if id "$username" &>/dev/null; then
            userdel "$username" 2>/dev/null || true
        fi

        # Remove ZFS dataset
        if zfs list "$pool/homes/$username" &>/dev/null; then
            zfs destroy "$pool/homes/$username" 2>/dev/null || true
        fi
    done

    # Remove all custom groups (keep smb_users for last)
    print_info "Removing groups..."
    echo "$state" | jq -r '.groups | keys[]' | while read -r groupname; do
        if [[ "$groupname" != "smb_users" ]]; then
            print_info "Removing group: $groupname"
            if getent group "$groupname" &>/dev/null; then
                groupdel "$groupname" 2>/dev/null || true
            fi
        fi
    done

    # Remove all shares
    print_info "Removing shares..."
    echo "$state" | jq -r '.shares | keys[]' | while read -r sharename; do
        if [[ "$sharename" != "shared" ]]; then
            print_info "Removing share: $sharename"
            local dataset
            dataset=$(echo "$state" | jq -r ".shares[\"$sharename\"].dataset")
            if zfs list "$dataset" &>/dev/null; then
                zfs destroy "$dataset" 2>/dev/null || true
            fi
        fi
    done

    # Remove base ZFS datasets
    print_info "Removing base ZFS datasets..."
    if zfs list "$pool/shared" &>/dev/null; then
        zfs destroy "$pool/shared" 2>/dev/null || true
    fi
    if zfs list "$pool/homes" &>/dev/null; then
        zfs destroy "$pool/homes" 2>/dev/null || true
    fi

    # Remove smb_users group
    if getent group smb_users &>/dev/null; then
        groupdel smb_users 2>/dev/null || true
    fi

    # Remove configuration files
    print_info "Removing configuration files..."
    if [[ -f "$SMB_CONF" ]]; then
        rm -f "$SMB_CONF"
    fi
    if [[ -f "$AVAHI_SMB_SERVICE" ]]; then
        rm -f "$AVAHI_SMB_SERVICE"
    fi

    # Stop services
    print_info "Stopping services..."
    systemctl stop smbd nmbd 2>/dev/null || true
    systemctl disable smbd nmbd 2>/dev/null || true

    # Remove state file
    if [[ -f "$STATE_FILE" ]]; then
        rm -f "$STATE_FILE"
    fi

    print_info "Uninstallation completed successfully!"
    echo "You may want to remove the samba packages manually if no longer needed:"
    echo "  apt-get remove samba samba-common-bin avahi-daemon"
}
