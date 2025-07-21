# Install business logic
install_business_logic() {
    local pool="$1"
    local macos_optimized="$2"
    local server_name=$(hostname)
    local workgroup="WORKGROUP"

    # Update packages and install
    print_info "Updating package list..."
    apt-get update

    print_info "Installing required packages..."
    apt-get install -y samba samba-common-bin avahi-daemon jq

    # Create ZFS datasets
    print_info "Creating ZFS datasets..."
    local homes_dataset="$pool/homes"
    local homes_mountpoint

    if ! zfs list "$homes_dataset" &>/dev/null; then
        zfs create "$homes_dataset"
    fi
    # Use zfs get mountpoint to determine actual path
    homes_mountpoint=$(zfs get -H -o value mountpoint "$homes_dataset")
    chmod 755 "$homes_mountpoint"

    # Create smb_users group
    if ! getent group smb_users &>/dev/null; then
        groupadd smb_users
        print_info "Created 'smb_users' group"
    fi

    # Configure Samba
    print_info "Configuring Samba..."
    backup_file "$SMB_CONF"

    create_smb_conf "$pool" "$server_name" "$workgroup" "$macos_optimized"

    # Configure Avahi
    print_info "Configuring Avahi..."
    backup_file "$AVAHI_SMB_SERVICE"

    create_avahi_conf "$server_name"

    # Test configuration
    if ! testparm -s "$SMB_CONF" &>/dev/null; then
        print_error "Samba configuration test failed"
        exit 1
    fi

    # Start services
    print_info "Starting services..."
    systemctl enable smbd nmbd avahi-daemon
    systemctl restart smbd nmbd avahi-daemon

    # Update state
    set_state_value "initialized" "true"
    set_state_value "zfs_pool" "$pool"
    set_state_value "server_name" "$server_name"
    set_state_value "workgroup" "$workgroup"
    set_state_value "macos_optimized" "$macos_optimized"

    # Add built-in shares to state
    local shared_config
    shared_config=$(jq -n \
                    --arg path "/$pool/shared" \
                    --arg comment "Shared Files" \
                    --arg browseable true \
                    --arg read_only false \
                    --arg valid_users "@smb_users" \
                    '{path: $path, comment: $comment, browseable: ($browseable | fromjson), read_only: ($read_only | fromjson), valid_users: $valid_users}')
    add_to_state_object "shares" "shared" "$shared_config"

    # Add smb_users group to state
    local group_config
    group_config=$(jq -n \
                   --arg description "Samba Users Group" \
                   '{description: $description, members: []}')
    add_to_state_object "groups" "smb_users" "$group_config"
}

---

# Install command
cmd_install() {
    local pool="$1"
    local macos_opt="$2"

    if [[ -z "$pool" ]]; then
        print_error "Pool name is required"
        show_usage
        exit 1
    fi

    # Check if already initialized
    local initialized
    initialized=$(get_state_value "initialized" "false")
    if [[ "$initialized" == "true" ]]; then
        print_error "System already initialized. Use 'modify setup' to change configuration."
        exit 1
    fi

    # Check if ZFS pool exists
    if ! zpool status "$pool" &>/dev/null; then
        print_error "ZFS pool '$pool' does not exist"
        exit 1
    fi

    local server_name
    server_name=$(hostname)
    local workgroup="WORKGROUP"
    local macos_optimized="false"

    if [[ "$macos_opt" == "--macos" ]]; then
        macos_optimized="true"
    fi

    local homes_dataset="$pool/homes"
    local homes_mountpoint

    if zfs list "$homes_dataset" &>/dev/null; then
        homes_mountpoint=$(zfs get -H -o value mountpoint "$homes_dataset")
        print_warning "ZFS dataset '$homes_dataset' already exists with mountpoint '$homes_mountpoint'."
        echo "Do you want to continue? (y/N):"
        read -r confirm
        if ! [[ "$confirm" =~ ^[Yy]$ ]]; then
            echo "Installation cancelled."
            exit 0
        fi
    fi

    print_info "Setting up Samba with ZFS integration"
    echo ""
    echo "=== Summary ==="
    echo "Pool: $pool"
    echo "Server: $server_name"
    echo "Workgroup: $workgroup"
    echo "macOS optimized: $macos_optimized"
    echo ""
    echo "Continue? (y/N):"
    read -r confirm
    if ! [[ "$confirm" =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi

    install_business_logic "$pool" "$macos_optimized"

    print_info "Installation completed successfully!"
    echo ""
    echo "Next steps:"
    echo "  - Create users: $SCRIPT_NAME create user <username>"
    echo "  - Create shares: $SCRIPT_NAME create share <sharename>"
    echo "  - List created items: $SCRIPT_NAME list users|shares|groups"
}