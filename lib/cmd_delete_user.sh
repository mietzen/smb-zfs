# Delete user
cmd_delete_user() {
    local username="$1"

    check_initialized

    if [[ -z "$username" ]]; then
        print_error "Username is required"
        exit 1
    fi

    # Check if user exists in state
    local state
    state=$(read_state)
    if ! echo "$state" | jq -e ".users[\"$username\"]" &>/dev/null; then
        print_error "User '$username' is not managed by this tool"
        exit 1
    fi

    local pool
    pool=$(get_state_value "zfs_pool" "")

    print_info "Removing user: $username"
    print_warning "This will remove:"
    echo "  - System user account"
    echo "  - Samba user account"
    echo "  - ZFS dataset: $pool/homes/$username"
    echo "  - All data in home directory"
    echo ""

    echo "Are you sure? Type 'DELETE' to confirm:"
    read -r confirm
    if [[ "$confirm" != "DELETE" ]]; then
        echo "User deletion cancelled."
        exit 0
    fi

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

    # Remove ZFS dataset
    print_info "Removing ZFS dataset..."
    if zfs list "$pool/homes/$username" &>/dev/null; then
        zfs destroy "$pool/homes/$username"
    fi

    # Remove from state
    remove_from_state_object "users" "$username"

    print_info "User '$username' deleted successfully!"
}
