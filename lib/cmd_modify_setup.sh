# Modify setup
# TODO: check jq expression
# TODO: Use read -r -p
# TODO: Check if all escaping in jq is needed
cmd_modify_setup() {
    check_initialized

    print_info "Modifying server configuration"

    local current_server_name
    current_server_name=$(get_state_value "server_name" "")
    local current_workgroup
    current_workgroup=$(get_state_value "workgroup" "")
    local current_macos
    current_macos=$(get_state_value "macos_optimized" "false")
    local pool
    pool=$(get_state_value "zfs_pool" "")

    echo "Current configuration:"
    echo "  Server name: $current_server_name"
    echo "  Workgroup: $current_workgroup"
    echo "  macOS optimized: $current_macos"
    echo "  ZFS pool: $pool (cannot be changed)"
    echo ""

    echo "Enter new server name [current: $current_server_name]:"
    read -r new_server_name
    if [[ -z "$new_server_name" ]]; then
        new_server_name="$current_server_name"
    fi

    echo "Enter new workgroup [current: $current_workgroup]:"
    read -r new_workgroup
    if [[ -z "$new_workgroup" ]]; then
        new_workgroup="$current_workgroup"
    fi

    echo "Enable macOS optimization? (y/n) [current: $current_macos]:"
    read -r macos_input
    if [[ -z "$macos_input" ]]; then
        new_macos="$current_macos"
    elif [[ "$macos_input" =~ ^[Yy]$ ]]; then
        new_macos="true"
    else
        new_macos="false"
    fi

    echo ""
    echo "=== Summary of Changes ==="
    echo "Server name: $current_server_name -> $new_server_name"
    echo "Workgroup: $current_workgroup -> $new_workgroup"
    echo "macOS optimized: $current_macos -> $new_macos"
    echo ""

    echo "Apply changes? (y/N):"
    read -r confirm
    if ! [[ "$confirm" =~ ^[Yy]$ ]]; then
        echo "Modification cancelled."
        exit 0
    fi

    # Update Samba configuration
    print_info "Updating Samba configuration..."
    backup_file "$SMB_CONF"

    create_smb_conf "$pool" "$new_server_name" "$new_workgroup" "$new_macos"

    # Re-add all shares from state
    local state
    state=$(read_state)
    echo "$state" | jq -r '.shares | to_entries[]' | while IFS= read -r share_entry; do
        local share_name
        share_name=$(echo "$share_entry" | jq -r '.key')
        local share_config
        share_config=$(echo "$share_entry" | jq -r '.value')

        # Skip built-in shares as they're already in the base config
        if [[ "$share_name" == "shared" ]]; then
            continue
        fi

        local comment
        comment=$(echo "$share_config" | jq -r '.comment')
        local path
        path=$(echo "$share_config" | jq -r '.path')
        local browseable
        browseable=$(echo "$share_config" | jq -r '.browseable')
        local read_only
        read_only=$(echo "$share_config" | jq -r '.read_only')
        local valid_users
        valid_users=$(echo "$share_config" | jq -r '.valid_users')
        local owner
        owner=$(echo "$share_config" | jq -r '.owner')
        local group
        group=$(echo "$share_config" | jq -r '.group')

        cat >> "$SMB_CONF" << EOF

[$share_name]
    comment = $comment
    path = $path
    browseable = $browseable
    read only = $read_only
    create mask = 0664
    directory mask = 0775
    valid users = $valid_users
    force user = $owner
    force group = $group
EOF
    done

    # Test and reload
    if ! testparm -s "$SMB_CONF" &>/dev/null; then
        print_error "Samba configuration test failed"
        exit 1
    fi

    systemctl reload smbd nmbd avahi-daemon

    # Update state
    set_state_value "server_name" "$new_server_name"
    set_state_value "workgroup" "$new_workgroup"
    set_state_value "macos_optimized" "$new_macos"

    print_info "Server configuration updated successfully!"
}
