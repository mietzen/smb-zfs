# Create share business logic function
create_share_business_logic() {
    local sharename="$1"
    local comment="$2"
    local dataset_path="$3"
    local owner="$4"
    local group="$5"
    local perms="$6"
    local valid_users="$7"
    local readonly="$8"
    local browseable="$9"
    
    local pool
    pool=$(get_state_value "zfs_pool" "")
    local dataset_full="$pool/$dataset_path"
    local mount_point="/$pool/$dataset_path"
    
    # Create ZFS dataset
    print_info "Creating ZFS dataset..."
    if ! zfs list "$dataset_full" &>/dev/null; then
        zfs create "$dataset_full"
    fi
    
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
}

# Create share
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
    
    local dataset_full="$pool/$dataset_path"
    
    # Check if dataset already exists and get actual mountpoint
    local actual_mountpoint
    actual_mountpoint=$(zfs get -H -o value mountpoint "$dataset_full" 2>/dev/null)
    if [[ $? -eq 0 ]]; then
        print_warning "ZFS dataset $dataset_full already exists at $actual_mountpoint"
        echo "Do you want to continue? (y/N):"
        read -r continue_choice
        if [[ "$continue_choice" != "y" && "$continue_choice" != "Y" ]]; then
            print_info "Operation cancelled"
            exit 0
        fi
    fi

    echo "Enter owner username [default: root]:"
    read -r owner
    if [[ -z "$owner" ]]; then
        owner="root"
    fi
    
    # Validate owner against state
    if [[ "$owner" != "root" ]]; then
        local available_users
        available_users=$(get_state_object_keys "users")
        if [[ -n "$available_users" ]] && ! echo "$available_users" | grep -q "^$owner$"; then
            print_error "User '$owner' not found in state"
            exit 1
        fi
    fi

    echo "Enter system group name [default: smb_users]:"
    read -r group
    if [[ -z "$group" ]]; then
        group="smb_users"
    fi
    
    # Show available groups from state
    echo ""
    echo "Available groups from state:"
    local available_groups
    available_groups=$(get_state_object_keys "groups")
    if [[ -n "$available_groups" ]]; then
        echo "$available_groups" | while read -r grp; do
            echo " - $grp"
        done
    else
        print_warning "No groups defined in state"
    fi
    
    # Validate group against state (if not default system groups)
    if [[ "$group" != "smb_users" && "$group" != "root" ]]; then
        if [[ -n "$available_groups" ]] && ! echo "$available_groups" | grep -q "^$group$"; then
            print_error "Group '$group' not found in state"
            exit 1
        fi
    fi

    echo "Enter permissions [default: 775]:"
    read -r perms
    if [[ -z "$perms" ]]; then
        perms="775"
    fi

    echo ""
    echo "Available users from state:"
    local available_users
    available_users=$(get_state_object_keys "users")
    if [[ -n "$available_users" ]]; then
        echo "$available_users" | while read -r usr; do
            echo " - $usr"
        done
    else
        print_warning "No users defined in state"
    fi
    
    echo "Valid SMB users (comma-separated, @ for groups, or * for all) [default: @smb_users]:"
    read -r valid_users
    if [[ -z "$valid_users" ]]; then
        valid_users="@smb_users"
    fi
    
    # Validate users in valid_users against state
    if [[ "$valid_users" != "*" && "$valid_users" != "@smb_users" ]]; then
        IFS=',' read -ra user_list <<< "$valid_users"
        for user_entry in "${user_list[@]}"; do
            user_entry=$(echo "$user_entry" | xargs) # trim whitespace
            if [[ "$user_entry" != @* ]]; then # not a group reference
                if [[ -n "$available_users" ]] && ! echo "$available_users" | grep -q "^$user_entry$"; then
                    print_error "User '$user_entry' not found in state"
                    exit 1
                fi
            fi
        done
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

    # Execute business logic
    create_share_business_logic "$sharename" "$comment" "$dataset_path" "$owner" "$group" "$perms" "$valid_users" "$readonly" "$browseable"

    print_info "Share '$sharename' created successfully!"
    echo "Access via: \\\\$(hostname)\\$sharename"
}