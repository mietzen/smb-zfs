# Delete share business logic function
delete_share_business_logic() {
    local sharename="$1"
    local delete_data="$2"  # true/false
    
    check_initialized
    
    # Check if share exists in state
    local state
    state=$(read_state)
    if ! echo "$state" | jq -e ".shares[\"$sharename\"]" &>/dev/null; then
        print_error "Share '$sharename' is not managed by this tool"
        return 1
    fi
    
    local dataset
    dataset=$(echo "$state" | jq -r ".shares[\"$sharename\"].dataset")
    
    print_info "Removing share: $sharename"
    
    # Remove from Samba config
    print_info "Removing from Samba configuration..."
    backup_file "$SMB_CONF"
    # Remove share section from config (simple approach)
    sed -i "/^\[$sharename\]/,/^$/d" "$SMB_CONF"
    
    # Test configuration
    if ! testparm -s "$SMB_CONF" &>/dev/null; then
        print_error "Samba configuration test failed"
        return 1
    fi
    
    systemctl reload smbd
    
    # Handle ZFS dataset based on delete_data flag
    if [[ "$delete_data" == "true" ]]; then
        print_info "Removing ZFS dataset..."
        if zfs list "$dataset" &>/dev/null; then
            zfs destroy "$dataset"
        fi
    else
        print_info "ZFS dataset '$dataset' preserved (use --delete-data to remove)"
    fi
    
    # Remove from state
    remove_from_state_object "shares" "$sharename"
    
    print_info "Share '$sharename' deleted successfully!"
    return 0
}

# Delete share
cmd_delete_share() {
    local sharename="$1"
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
    
    if [[ -z "$sharename" ]]; then
        print_error "Share name is required"
        exit 1
    fi
    
    # Get dataset info for warning
    local state
    state=$(read_state)
    local dataset
    dataset=$(echo "$state" | jq -r ".shares[\"$sharename\"].dataset" 2>/dev/null || echo "")
    
    print_warning "This will remove:"
    echo " - Samba share configuration"
    if [[ "$delete_data" == "true" ]]; then
        echo " - ZFS dataset: $dataset"
        echo ""
        echo "⚠️  WARNING: ALL DATA IN THE SHARE WILL BE PERMANENTLY LOST! ⚠️"
        echo "⚠️  THIS CANNOT BE UNDONE! ⚠️"
    else
        echo " - ZFS dataset will be PRESERVED"
        echo ""
        echo "Note: Data will remain in dataset '$dataset'"
        echo "Use --delete-data flag to permanently delete all data"
    fi
    echo ""
    echo "Are you sure? Type 'DELETE' to confirm:"
    read -r confirm
    
    if [[ "$confirm" != "DELETE" ]]; then
        echo "Share deletion cancelled."
        exit 0
    fi
    
    # Call business logic function
    delete_share_business_logic "$sharename" "$delete_data"
}