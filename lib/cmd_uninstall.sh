# Uninstall business logic
# Performs the core uninstallation steps without user interaction.
uninstall_business_logic() {
    local delete_data="$1"
    local delete_users="$2"

    local pool
    pool=$(get_state_value "zfs_pool" "")
    local state
    state=$(read_state)

    # Remove all users and groups if requested
    if [[ "$delete_users" == true ]]; then
        print_info "Removing users..."
        # Loop through each user in the state file
        echo "$state" | jq -r '.users | keys[]' | while read -r username; do
            print_info "Removing user: $username"
            # Remove from Samba password database
            if pdbedit -L | grep -q "^$username:"; then
                smbpasswd -x "$username" >/dev/null 2>&1 || true
            fi
            # Remove system user account
            if id "$username" &>/dev/null; then
                userdel "$username" >/dev/null 2>&1 || true
            fi
        done

        print_info "Removing groups..."
        # Remove all custom groups, saving smb_users for last
        echo "$state" | jq -r '.groups | keys[]' | while read -r groupname; do
            if [[ "$groupname" != "smb_users" ]]; then
                print_info "Removing group: $groupname"
                if getent group "$groupname" &>/dev/null; then
                    groupdel "$groupname" >/dev/null 2>&1 || true
                fi
            fi
        done

        # Remove the main smb_users group
        if getent group smb_users &>/dev/null; then
            groupdel smb_users >/dev/null 2>&1 || true
        fi
    fi

    # Remove all ZFS datasets if requested
    if [[ "$delete_data" == true && -n "$pool" ]]; then
        print_info "Removing user home datasets..."
        # Destroy each user's home directory dataset
        echo "$state" | jq -r '.users | keys[]' | while read -r username; do
            if zfs list "$pool/homes/$username" &>/dev/null; then
                print_info "Destroying dataset: $pool/homes/$username"
                zfs destroy -r "$pool/homes/$username" >/dev/null 2>&1 || true
            fi
        done

        print_info "Removing share datasets..."
        # Destroy each custom share's dataset
        echo "$state" | jq -r '.shares | keys[]' | while read -r sharename; do
            local dataset
            dataset=$(echo "$state" | jq -r ".shares[\"$sharename\"].dataset")
            if [[ -n "$dataset" && "$dataset" != "null" ]] && zfs list "$dataset" &>/dev/null; then
                print_info "Destroying dataset: $dataset"
                zfs destroy -r "$dataset" >/dev/null 2>&1 || true
            fi
        done

        # Remove the base 'homes' dataset
        if zfs list "$pool/homes" &>/dev/null; then
            print_info "Destroying dataset: $pool/homes"
            zfs destroy -r "$pool/homes" >/dev/null 2>&1 || true
        fi
    fi

    # Stop and disable services
    print_info "Stopping and disabling services..."
    systemctl stop smbd nmbd avahi-daemon >/dev/null 2>&1 || true
    systemctl disable smbd nmbd avahi-daemon >/dev/null 2>&1 || true

    # Remove configuration files
    print_info "Removing configuration files..."
    rm -f "$SMB_CONF" "$AVAHI_SMB_SERVICE"

    # Remove the state file itself
    rm -f "$STATE_FILE"

    # Uninstall the packages
    print_info "Uninstalling packages..."
    apt-get purge -y --auto-remove samba samba-common-bin avahi-daemon

    print_info "Uninstallation completed successfully!"
}

# Uninstall command
# Guides the user through the uninstallation process.
cmd_uninstall() {
    check_initialized

    local delete_data=false
    local delete_users=false

    # Parse command-line options
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

    # Display what will be removed
    print_info "This will remove the following:"
    echo " - All Samba & Avahi configurations created by this tool"
    echo " - Systemd services for Samba & Avahi"
    echo " - The script's state file"
    echo " - The installed packages (samba, avahi-daemon, etc.)"

    if [[ "$delete_users" == true ]]; then
        print_warning " - All users and groups created by this tool will be deleted."
    fi

    if [[ "$delete_data" == true ]]; then
        print_warning " - All ZFS datasets (HOME DIRECTORIES AND SHARES) will be destroyed."
    fi
    echo ""

    # Display strong warnings for destructive actions
    if [[ "$delete_data" == true ]]; then
        print_warning "⚠️  WARNING: THIS WILL PERMANENTLY DELETE ALL USER DATA! ⚠️"
        print_warning "All home directories and shared folders will be IRREVERSIBLY LOST!"
        print_warning "Ensure you have backed up any important data before proceeding."
        echo ""
    fi
    if [[ "$delete_users" == true ]]; then
        print_warning "⚠️  WARNING: THIS WILL DELETE SYSTEM USERS AND GROUPS! ⚠️"
        print_warning "All users created by this tool will be permanently removed."
        echo ""
    fi

    # Require explicit confirmation from the user
    if [[ "$delete_data" == true || "$delete_users" == true ]]; then
        echo "This is a destructive operation. To proceed, you must type:"
        echo "I UNDERSTAND THE CONSEQUENCES"
        read -r -p "> " confirm
        if [[ "$confirm" != "I UNDERSTAND THE CONSEQUENCES" ]]; then
            echo "Confirmation failed. Uninstallation cancelled."
            exit 0
        fi
    else
        echo "To confirm the removal of configurations and packages, type 'UNINSTALL':"
        read -r -p "> " confirm
        if [[ "$confirm" != "UNINSTALL" ]]; then
            echo "Uninstallation cancelled."
            exit 0
        fi
    fi

    # Execute the uninstallation logic
    uninstall_business_logic "$delete_data" "$delete_users"
}
