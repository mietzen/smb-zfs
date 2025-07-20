
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

    print_info "Setting up Samba with ZFS integration"
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

    # Update packages and install
    print_info "Updating package list..."
    apt-get update

    print_info "Installing required packages..."
    apt-get install -y samba samba-common-bin avahi-daemon jq

    # Create ZFS datasets
    print_info "Creating ZFS datasets..."
    local homes_dataset="$pool/homes"
    local shared_dataset="$pool/shared"

    if ! zfs list "$homes_dataset" &>/dev/null; then
        zfs create "$homes_dataset"
        chmod 755 "/$pool/homes"
    fi

    if ! zfs list "$shared_dataset" &>/dev/null; then
        zfs create "$shared_dataset"
        chmod 775 "/$pool/shared"
    fi

    # Create smb_users group
    if ! getent group smb_users &>/dev/null; then
        groupadd smb_users
        print_info "Created 'smb_users' group"
    fi

    chown root:smb_users "/$pool/shared"

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
    local shared_config="{\"path\": \"/$pool/shared\", \"comment\": \"Shared Files\", \"browseable\": true, \"read_only\": false, \"valid_users\": \"@smb_users\"}"
    add_to_state_object "shares" "shared" "$shared_config"

    # Add smb_users group to state
    local group_config="{\"description\": \"Samba Users Group\", \"members\": []}"
    add_to_state_object "groups" "smb_users" "$group_config"

    print_info "Installation completed successfully!"
    echo ""
    echo "Next steps:"
    echo "  - Create users: $SCRIPT_NAME create user <username>"
    echo "  - Create shares: $SCRIPT_NAME create share <sharename>"
    echo "  - List created items: $SCRIPT_NAME list users|shares|groups"
}

# Create SMB configuration
create_smb_conf() {
    local pool="$1"
    local server_name="$2"
    local workgroup="$3"
    local macos_optimized="$4"

    cat > "$SMB_CONF" << EOF
# Samba configuration file created by $SCRIPT_NAME
# $(date)

[global]
    # Basic server settings
    workgroup = $workgroup
    server string = $server_name Samba Server
    netbios name = $server_name

    # Security settings
    security = user
    map to guest = never
    passdb backend = tdbsam

    # Network settings
    dns proxy = no

    # Logging
    log file = /var/log/samba/log.%m
    max log size = 1000
    log level = 1

    # Performance
    socket options = TCP_NODELAY IPTOS_LOWDELAY SO_RCVBUF=524288 SO_SNDBUF=524288

    # Avahi/Zeroconf support
    multicast dns register = yes

    # File creation settings
    create mask = 0664
    directory mask = 0775
    force create mode = 0664
    force directory mode = 0775
EOF

    if [[ "$macos_optimized" == "true" ]]; then
        cat >> "$SMB_CONF" << EOF

    # Mac compatibility with vfs_fruit
    vfs objects = fruit streams_xattr
    fruit:metadata = stream
    fruit:model = MacSamba
    fruit:posix_rename = yes
    fruit:veto_appledouble = no
    fruit:wipe_intentionally_left_blank_rfork = yes
    fruit:delete_empty_adfiles = yes
EOF
    fi

    cat >> "$SMB_CONF" << EOF

# User home directories
[homes]
    comment = Home Directories
    path = /$pool/homes/%S
    browseable = no
    read only = no
    create mask = 0700
    directory mask = 0700
    valid users = %S
    force user = %S

# Shared directory
[shared]
    comment = Shared Files
    path = /$pool/shared
    browseable = yes
    read only = no
    create mask = 0664
    directory mask = 0775
    valid users = @smb_users
EOF
}
