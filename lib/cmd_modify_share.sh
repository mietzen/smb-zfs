# Modify share
# TODO: check jq expression
# TODO: Use read -r -p
cmd_modify_share() {
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

    print_info "Modifying share: $sharename"

    # Get current configuration
    local current_config
    current_config=$(echo "$state" | jq -r ".shares[\"$sharename\"]")
    local current_comment
    current_comment=$(echo "$current_config" | jq -r '.comment')
    local current_valid_users
    current_valid_users=$(echo "$current_config" | jq -r '.valid_users')
    local current_readonly
    current_readonly=$(echo "$current_config" | jq -r '.read_only')
    local current_browseable
    current_browseable=$(echo "$current_config" | jq -r '.browseable')
    local current_perms
    current_perms=$(echo "$current_config" | jq -r '.permissions')
    local current_owner
    current_owner=$(echo "$current_config" | jq -r '.owner')
    local current_group
    current_group=$(echo "$current_config" | jq -r '.group')
    local share_path
    share_path=$(echo "$current_config" | jq -r '.path')

    echo "Current configuration:"
    echo "  Comment: $current_comment"
    echo "  Valid users: $current_valid_users"
    echo "  Read-only: $current_readonly"
    echo "  Browseable: $current_browseable"
    echo "  Permissions: $current_perms"
    echo "  Owner: $current_owner:$current_group"
    echo ""

    # Get new configuration
    echo "Enter new comment [current: $current_comment]:"
    read -r new_comment
    if [[ -z "$new_comment" ]]; then
        new_comment="$current_comment"
    fi

    echo "Available users and groups:"
    echo "Users:"
    get_state_object_keys "users" | while read -r user; do
        echo "  - $user"
    done
    echo "Groups:"
    get_state_object_keys "groups" | while read -r group; do
        echo "  - @$group"
    done
    echo ""
    echo "Enter valid users [current: $current_valid_users]:"
    read -r new_valid_users
    if [[ -z "$new_valid_users" ]]; then
        new_valid_users="$current_valid_users"
    fi

    echo "Read-only? (y/n) [current: $current_readonly]:"
    read -r readonly_input
    if [[ -z "$readonly_input" ]]; then
        new_readonly="$current_readonly"
    elif [[ "$readonly_input" =~ ^[Yy]$ ]]; then
        new_readonly="yes"
    else
        new_readonly="no"
    fi

    echo "Browseable? (y/n) [current: $current_browseable]:"
    read -r browseable_input
    if [[ -z "$browseable_input" ]]; then
        new_browseable="$current_browseable"
    elif [[ "$browseable_input" =~ ^[Yy]$ ]]; then
        new_browseable="yes"
    else
        new_browseable="no"
    fi

    echo "Enter permissions [current: $current_perms]:"
    read -r new_perms
    if [[ -z "$new_perms" ]]; then
        new_perms="$current_perms"
    fi

    echo "Enter owner [current: $current_owner]:"
    read -r new_owner
    if [[ -z "$new_owner" ]]; then
        new_owner="$current_owner"
    fi

    echo "Enter group [current: $current_group]:"
    read -r new_group
    if [[ -z "$new_group" ]]; then
        new_group="$current_group"
    fi

    echo ""
    echo "=== Summary of Changes ==="
    echo "Share: $sharename"
    echo "Comment: $current_comment -> $new_comment"
    echo "Valid users: $current_valid_users -> $new_valid_users"
    echo "Read-only: $current_readonly -> $new_readonly"
    echo "Browseable: $current_browseable -> $new_browseable"
    echo "Permissions: $current_perms -> $new_perms"
    echo "Owner: $current_owner:$current_group -> $new_owner:$new_group"
    echo ""

    echo "Apply changes? (y/N):"
    read -r confirm
    if ! [[ "$confirm" =~ ^[Yy]$ ]]; then
        echo "Modification cancelled."
        exit 0
    fi

    # Update file system permissions
    print_info "Updating file system permissions..."
    chown "$new_owner:$new_group" "$share_path"
    chmod "$new_perms" "$share_path"

    # Update Samba configuration
    print_info "Updating Samba configuration..."
    backup_file "$SMB_CONF"

    # Remove old share section and add new one
    sed -i "/^\[$sharename\]/,/^$/d" "$SMB_CONF"
    cat >> "$SMB_CONF" << EOF

[$sharename]
    comment = $new_comment
    path = $share_path
    browseable = $new_browseable
    read only = $new_readonly
    create mask = 0664
    directory mask = 0775
    valid users = $new_valid_users
    force user = $new_owner
    force group = $new_group
EOF

    # Test and reload
    if ! testparm -s "$SMB_CONF" &>/dev/null; then
        print_error "Samba configuration test failed"
        exit 1
    fi

    systemctl reload smbd

    # Update state
    local updated_config
    updated_config=$(echo "$current_config" | jq \
        --arg comment "$new_comment" \
        --arg valid_users "$new_valid_users" \
        --arg read_only "$new_readonly" \
        --arg browseable "$new_browseable" \
        --arg permissions "$new_perms" \
        --arg owner "$new_owner" \
        --arg group "$new_group" \
        '.comment = $comment | .valid_users = $valid_users | .read_only = $read_only | .browseable = $browseable | .permissions = $permissions | .owner = $owner | .group = $group')

    add_to_state_object "shares" "$sharename" "$updated_config"

    print_info "Share '$sharename' modified successfully!"
}
