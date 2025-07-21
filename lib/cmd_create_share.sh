
# Create share
# TODO: Check if all escaping in jq is needed
# TODO: Use zfs get mountpoint to determine actual path, if share already exists, also print_warning and prompt if you want to continue
# TODO: Show available groups and users from state, fail if user / group not in state
cmd_create_share() {
    local sharename="$1"

    check_initialized

    if [[ -z "$sharename" ]]; then
        print_error "Share name is required"
        exit 1
    fi

    # Validate share name
    if ! [[ "$sharename" =~ ^[a-zA-Z0-9._-]+$ ]]; then
        print_error "Share name contains invalid characters"
        exit 1
    fi

    # Check if share already exists
    local state
    state=$(read_state)
    if echo "$state" | jq -e ".shares[\"$sharename\"]" &>/dev/null; then
        print_error "Share '$sharename' already managed by this tool"
        exit 1
    fi

    local pool
    pool=$(get_state_value "zfs_pool" "")

    print_info "Creating share: $sharename"

    # Get share configuration
    echo "Enter share comment [default: $sharename Share]:"
    read -r comment
    if [[ -z "$comment" ]]; then
        comment="$sharename Share"
    fi

    echo "Enter dataset path [default: $sharename]:"
    read -r dataset_path
    if [[ -z "$dataset_path" ]]; then
        dataset_path="$sharename"
    fi

    echo "Enter owner username [default: root]:"
    read -r owner
    if [[ -z "$owner" ]]; then
        owner="root"
    fi

    echo "Enter system group name [default: smb_users]:"
    read -r group
    if [[ -z "$group" ]]; then
        group="smb_users"
    fi

    echo "Enter permissions [default: 775]:"
    read -r perms
    if [[ -z "$perms" ]]; then
        perms="775"
    fi

    echo "Valid SMB users (comma-separated, @ for groups, or * for all) [default: @smb_users]:"
    read -r valid_users
    if [[ -z "$valid_users" ]]; then
        valid_users="@smb_users"
    fi

    echo "Read-only? (y/N):"
    read -r readonly
    if [[ "$readonly" =~ ^[Yy]$ ]]; then
        readonly="yes"
    else
        readonly="no"
    fi

    echo "Browseable? (Y/n):"
    read -r browseable
    if [[ "$browseable" =~ ^[Nn]$ ]]; then
        browseable="no"
    else
        browseable="yes"
    fi

    local dataset_full="$pool/$dataset_path"

    echo ""
    echo "=== Summary ==="
    echo "Share name: $sharename"
    echo "Dataset: $dataset_full"
    echo "Owner: $owner:$group"
    echo "Permissions: $perms"
    echo "Valid users: $valid_users"
    echo "Read-only: $readonly"
    echo "Browseable: $browseable"
    echo ""

    echo "Create share? (y/N):"
    read -r confirm
    if ! [[ "$confirm" =~ ^[Yy]$ ]]; then
        echo "Share creation cancelled."
        exit 0
    fi

    # Create ZFS dataset
    print_info "Creating ZFS dataset..."
    if ! zfs list "$dataset_full" &>/dev/null; then
        zfs create "$dataset_full"
    fi

    local mount_point="/$pool/$dataset_path"

    # Set permissions
    chown "$owner:$group" "$mount_point"
    chmod "$perms" "$mount_point"

    # Add to Samba config
    print_info "Adding to Samba configuration..."
    cat >> "$SMB_CONF" << EOF

[$sharename]
    comment = $comment
    path = $mount_point
    browseable = $browseable
    read only = $readonly
    create mask = 0664
    directory mask = 0775
    valid users = $valid_users
    force user = $owner
    force group = $group
EOF

    # Test and reload
    if ! testparm -s "$SMB_CONF" &>/dev/null; then
        print_error "Samba configuration test failed"
        exit 1
    fi

    systemctl reload smbd

    # Add to state
    local share_config="{\"dataset\": \"$dataset_full\", \"path\": \"$mount_point\", \"comment\": \"$comment\", \"owner\": \"$owner\", \"group\": \"$group\", \"permissions\": \"$perms\", \"valid_users\": \"$valid_users\", \"read_only\": \"$readonly\", \"browseable\": \"$browseable\", \"created\": \"$(date -Iseconds)\"}"
    add_to_state_object "shares" "$sharename" "$share_config"

    print_info "Share '$sharename' created successfully!"
    echo "Access via: \\\\$(hostname)\\$sharename"
}
