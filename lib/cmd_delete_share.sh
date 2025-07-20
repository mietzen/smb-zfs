# Delete share
# TODO: Add --delete-data option to delete zfs dataset, don't delete data by default, give a more alarming note
cmd_delete_share() {
    local sharename="$1"

    check_initialized

    if [[ -z "$sharename" ]]; then
        print_error "Share name is required"
        exit 1
    fi

    # Check if share exists in state
    local state
    state=$(read_state)
    if ! echo "$state" | jq -e ".shares[\"$sharename\"]" &>/dev/null; then
        print_error "Share '$sharename' is not managed by this tool"
        exit 1
    fi

    local dataset
    dataset=$(echo "$state" | jq -r ".shares[\"$sharename\"].dataset")

    print_info "Removing share: $sharename"
    print_warning "This will remove:"
    echo "  - Samba share configuration"
    echo "  - ZFS dataset: $dataset"
    echo "  - All data in the share"
    echo ""

    echo "Are you sure? Type 'DELETE' to confirm:"
    read -r confirm
    if [[ "$confirm" != "DELETE" ]]; then
        echo "Share deletion cancelled."
        exit 0
    fi

    # Remove from Samba config
    print_info "Removing from Samba configuration..."
    backup_file "$SMB_CONF"

    # Remove share section from config (simple approach)
    sed -i "/^\[$sharename\]/,/^$/d" "$SMB_CONF"

    # Test configuration
    if ! testparm -s "$SMB_CONF" &>/dev/null; then
        print_error "Samba configuration test failed"
        exit 1
    fi

    systemctl reload smbd

    # Remove ZFS dataset
    print_info "Removing ZFS dataset..."
    if zfs list "$dataset" &>/dev/null; then
        zfs destroy "$dataset"
    fi

    # Remove from state
    remove_from_state_object "shares" "$sharename"

    print_info "Share '$sharename' deleted successfully!"
}
