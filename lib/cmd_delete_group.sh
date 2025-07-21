# Delete group business logic function
delete_group_business_logic() {
    local groupname="$1"
    
    check_initialized
    
    # Check if group exists in state
    local state
    state=$(read_state)
    if ! echo "$state" | jq -e ".groups[\"$groupname\"]" &>/dev/null; then
        print_error "Group '$groupname' is not managed by this tool"
        return 1
    fi
    
    # Don't allow deletion of smb_users group
    if [[ "$groupname" == "smb_users" ]]; then
        print_error "Cannot delete the 'smb_users' group"
        return 1
    fi
    
    print_info "Removing group: $groupname"
    
    # Remove system group
    print_info "Removing system group..."
    if getent group "$groupname" &>/dev/null; then
        groupdel "$groupname"
    fi
    
    # Remove from state
    remove_from_state_object "groups" "$groupname"
    
    print_info "Group '$groupname' deleted successfully!"
    return 0
}

# Delete group
cmd_delete_group() {
    local groupname="$1"
    
    if [[ -z "$groupname" ]]; then
        print_error "Group name is required"
        exit 1
    fi
    
    print_warning "This will remove the system group and all its memberships"
    echo ""
    echo "Are you sure? Type 'DELETE' to confirm:"
    read -r confirm
    
    if [[ "$confirm" != "DELETE" ]]; then
        echo "Group deletion cancelled."
        exit 0
    fi
    
    # Call business logic function
    delete_group_business_logic "$groupname"
}