# Delete user business logic function
delete_user_business_logic() {
    local username="$1"
    local delete_data="$2"  # true/false
    
    check_initialized
    
    # Check if user exists in state
    local state
    state=$(read_state)
    if ! echo "$state" | jq -e ".users[\"$username\"]" &>/dev/null; then
        print_error "User '$username' is not managed by this tool"
        return 1
    fi
    
    local pool
    pool=$(get_state_value "zfs_pool" "")
    
    print_info "Removing user: $username"
    
    # Remove from Samba
    print_info "Removing from Samba..."
    if pdbedit -L | grep -q "^$username:"; then
        smbpasswd -x "$username"
    fi
    
    # Remove system user
    print_info "Removing system user..."
    if id "$username" &>/dev/null; then
        userdel "$username"
    fi
    
    # Handle ZFS dataset based on delete_data flag
    if [[ "$delete_data" == "true" ]]; then
        print_info "Removing ZFS dataset..."
        if zfs list "$pool/homes/$username" &>/dev/null; then
            zfs destroy "$pool/homes/$username"
        fi
    else
        print_info "ZFS dataset '$pool/homes/$username' preserved (use --delete-data to remove)"
    fi
    
    # Remove from state
    remove_from_state_object "users" "$username"
    
    print_info "User '$username' deleted successfully!"
    return 0
}

# Delete user
cmd_delete_user() {
    local username="$1"
    shift
    local delete_data="false"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --delete-data)
                delete_data="true"
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    if [[ -z "$username" ]]; then
        print_error "Username is required"
        exit 1
    fi
    
    # Get pool info for warning
    local pool
    pool=$(get_state_value "zfs_pool" "")
    
    print_warning "This will remove:"
    echo " - System user account"
    echo " - Samba user account"
    if [[ "$delete_data" == "true" ]]; then
        echo " - ZFS dataset: $pool/homes/$username"
        echo ""
        echo "⚠️  WARNING: ALL USER DATA WILL BE PERMANENTLY LOST! ⚠️"
        echo "⚠️  THIS CANNOT BE UNDONE! ⚠️"
    else
        echo " - ZFS dataset will be PRESERVED"
        echo ""
        echo "Note: User data will remain in dataset '$pool/homes/$username'"
        echo "Use --delete-data flag to permanently delete all user data"
    fi
    echo ""
    echo "Are you sure? Type 'DELETE' to confirm:"
    read -r confirm
    
    if [[ "$confirm" != "DELETE" ]]; then
        echo "User deletion cancelled."
        exit 0
    fi
    
    # Call business logic function
    delete_user_business_logic "$username" "$delete_data"
}