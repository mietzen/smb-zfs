# Install business logic
# Performs the core installation and configuration steps without user interaction.
install_business_logic() {
    local pool="$1"
    local server_name="$2"
    local workgroup="$3"
    local macos_optimized="$4"
    local homes_mountpoint="$5"

    # Update packages and install required software
    print_info "Updating package list..."
    apt-get update

    print_info "Installing required packages..."
    apt-get install -y samba samba-common-bin avahi-daemon jq

    # Create ZFS datasets if they don't exist
    print_info "Creating ZFS datasets..."
    local homes_dataset="$pool/homes"

    if ! zfs list "$homes_dataset" &>/dev/null; then
        zfs create "$homes_dataset"
    fi

    # Set permissions on the homes mountpoint
    chmod 755 "$homes_mountpoint"

    # Create smb_users group if it doesn't exist
    if ! getent group smb_users &>/dev/null; then
        groupadd smb_users
        print_info "Created 'smb_users' group"
    fi

    # Configure Samba
    print_info "Configuring Samba..."
    backup_file "$SMB_CONF"
    create_smb_conf "$pool" "$server_name" "$workgroup" "$macos_optimized"

    # Configure Avahi for service discovery
    print_info "Configuring Avahi..."
    backup_file "$AVAHI_SMB_SERVICE"
    create_avahi_conf "$server_name"

    # Test the new Samba configuration
    if ! testparm -s "$SMB_CONF" &>/dev/null; then
        print_error "Samba configuration test failed"
        # Note: In a real script, you might want to restore the backup here.
        exit 1
    fi

    # Enable and restart services
    print_info "Starting and enabling services..."
    systemctl enable smbd nmbd avahi-daemon
    systemctl restart smbd nmbd avahi-daemon

    # Update the state file with installation details
    set_state_value "initialized" "true"
    set_state_value "zfs_pool" "$pool"
    set_state_value "server_name" "$server_name"
    set_state_value "workgroup" "$workgroup"
    set_state_value "macos_optimized" "$macos_optimized"

    # Add built-in shares and groups to the state file
    # Using single quotes to avoid escaping inner double quotes
    local shared_config='{"path": "/'"$pool"'/shared", "comment": "Shared Files", "browseable": true, "read_only": false, "valid_users": "@smb_users"}'
    add_to_state_object "shares" "shared" "$shared_config"

    local group_config='{"description": "Samba Users Group", "members": []}'
    add_to_state_object "groups" "smb_users" "$group_config"
}

# Install command
# Guides the user through the initial setup process.
cmd_install() {
    local pool="$1"
    local macos_opt="$2"

    if [[ -z "$pool" ]]; then
        print_error "Pool name is required"
        show_usage
        exit 1
    fi

    # Check if the system has already been initialized
    local initialized
    initialized=$(get_state_value "initialized" "false")
    if [[ "$initialized" == "true" ]]; then
        print_error "System already initialized. Use 'modify setup' to change configuration."
        exit 1
    fi

    # Check if the specified ZFS pool exists
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

    # Check for existing homes dataset and get its mountpoint
    local homes_dataset="$pool/homes"
    local homes_mountpoint
    local homes_exists=false
    if zfs list "$homes_dataset" &>/dev/null; then
        homes_exists=true
        # Get the actual mountpoint for the dataset
        homes_mountpoint=$(zfs get -H -o value mountpoint "$homes_dataset")
    else
        # If it doesn't exist, the mountpoint will be the default path
        homes_mountpoint="/$pool/homes"
    fi

    # Present installation plan to the user
    print_info "Setting up Samba with ZFS integration"
    echo ""
    echo "=== Summary ==="
    echo "Pool: $pool"
    echo "Server: $server_name"
    echo "Workgroup: $workgroup"
    echo "macOS optimized: $macos_optimized"
    echo ""

    if [[ "$homes_exists" == "true" ]]; then
        print_warning "Homes dataset '$homes_dataset' already exists at '$homes_mountpoint' and will be used."
    fi

    # Confirm with the user before proceeding
    echo "Continue with installation? (y/N):"
    read -r confirm
    if ! [[ "$confirm" =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi

    # Execute the installation logic
    install_business_logic "$pool" "$server_name" "$workgroup" "$macos_optimized" "$homes_mountpoint"

    print_info "Installation completed successfully!"
    echo ""
    echo "Next steps:"
    echo "  - Create users: $SCRIPT_NAME create user <username>"
    echo "  - Create shares: $SCRIPT_NAME create share <sharename>"
    echo "  - List created items: $SCRIPT_NAME list users|shares|groups"
}