# Uninstall
cmd_uninstall() {
    check_initialized

    local delete_data=false
    local delete_users=false

    # Parse options
    while [[ $# -gt 0 ]]; do
        case $1 in
            --delete-data)
                delete_data=true
                shift
                ;;
            --delete-users)
                delete_users=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Usage: $0 uninstall [--delete-data] [--delete-users]"
                exit 1
                ;;
        esac
    done

    print_info "Removing configuration"
    print_warning "This will remove:"
    echo " - All Samba configuration"
    echo " - All Avahi configuration"
    echo " - State file"

    if [[ "$delete_users" == true ]]; then
        echo " - All users created by this tool"
        echo " - All groups created by this tool"
    fi

    if [[ "$delete_data" == true ]]; then
        echo " - All ZFS datasets (HOME DIRECTORIES AND SHARES)"
        echo ""
        print_warning "⚠️  WARNING: THIS WILL PERMANENTLY DELETE ALL USER DATA! ⚠️"
        echo ""
        print_warning "All home directories and shared folders will be IRREVERSIBLY LOST!"
        echo "Make sure you have backed up any important data before proceeding."
    fi

    if [[ "$delete_users" == true ]]; then
        echo ""
        print_warning "⚠️  WARNING: THIS WILL DELETE ALL USERS AND GROUPS! ⚠️"
        echo ""
        print_warning "All users created by this tool will be permanently removed!"
        echo "This may affect system access and permissions."
    fi

    echo ""
    if [[ "$delete_data" == true || "$delete_users" == true ]]; then
        echo "Type 'I KNOW WHAT I AM DOING' to confirm this destructive operation:"
        read -r -p "> " confirm
        if [[ "$confirm" != "I KNOW WHAT I AM DOING" ]]; then
            echo "Uninstallation cancelled."
            exit 0
        fi
    else
        echo "Type 'UNINSTALL' to confirm configuration removal:"
        read -r -p "> " confirm
        if [[ "$confirm" != "UNINSTALL" ]]; then
            echo "Uninstallation cancelled."
            exit 0
        fi
    fi

    local pool
    pool=$(get_state_value "zfs_pool" "")
    local state
    state=$(read_state)

    # Remove all users if requested
    if [[ "$delete_users" == true ]]; then
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

        # Remove smb_users group
        if getent group smb_users &>/dev/null; then
            groupdel smb_users 2>/dev/null || true
        fi
    fi

    # Remove ZFS datasets if requested
    if [[ "$delete_data" == true ]]; then
        # Remove user home datasets
        print_info "Removing user home datasets..."
        echo "$state" | jq -r '.users | keys[]' | while read -r username; do
            if zfs list "$pool/homes/$username" &>/dev/null; then
                print_info "Destroying dataset: $pool/homes/$username"
                zfs destroy "$pool/homes/$username" 2>/dev/null || true
            fi
        done

        # Remove all shares
        print_info "Removing share datasets..."
        echo "$state" | jq -r '.shares | keys[]' | while read -r sharename; do
            if [[ "$sharename" != "shared" ]]; then
                print_info "Removing share: $sharename"
                local dataset
                dataset=$(echo "$state" | jq -r ".shares[\"$sharename\"].dataset")
                if zfs list "$dataset" &>/dev/null; then
                    print_info "Destroying dataset: $dataset"
                    zfs destroy "$dataset" 2>/dev/null || true
                fi
            fi
        done

        # Remove base ZFS datasets
        print_info "Removing base ZFS datasets..."
        if zfs list "$pool/shared" &>/dev/null; then
            print_info "Destroying dataset: $pool/shared"
            zfs destroy "$pool/shared" 2>/dev/null || true
        fi
        if zfs list "$pool/homes" &>/dev/null; then
            print_info "Destroying dataset: $pool/homes"
            zfs destroy "$pool/homes" 2>/dev/null || true
        fi
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

    print_info "Uninstalling packages..."
    apt-get auto-remove -y samba samba-common-bin avahi-daemon

    print_info "Uninstallation completed successfully!"
}