# Create user business logic function
create_user_business_logic() {
    local username="$1"
    local allow_shell="$2"
    local password="$3"
    local additional_groups="$4"
    
    local pool
    pool=$(get_state_value "zfs_pool" "")
    
    # Create system user
    print_info "Creating system user..."
    if [[ "$allow_shell" == "true" ]]; then
        useradd -m -d "/$pool/homes/$username" -s /bin/bash "$username"
    else
        useradd -M -s /usr/sbin/nologin "$username"
    fi
    
    # Create ZFS dataset
    print_info "Creating ZFS dataset..."
    zfs create "$pool/homes/$username"
    chown "$username:$username" "/$pool/homes/$username"
    chmod 700 "/$pool/homes/$username"
    
    # Set system password if shell access
    if [[ "$allow_shell" == "true" ]]; then
        echo "$username:$password" | chpasswd
    fi
    
    # Add to Samba
    print_info "Adding to Samba..."
    (echo "$password"; echo "$password") | smbpasswd -a -s "$username"
    smbpasswd -e "$username"
    
    # Add to smb_users group
    usermod -a -G smb_users "$username"
    
    # Process additional groups
    local groups_array="[]"
    if [[ -n "$additional_groups" ]]; then
        IFS=',' read -ra group_list <<< "$additional_groups"
        for group in "${group_list[@]}"; do
            group=$(echo "$group" | xargs) # trim whitespace
            if getent group "$group" &>/dev/null; then
                usermod -a -G "$group" "$username"
                groups_array=$(echo "$groups_array" | jq ". + [\"$group\"]")
            else
                print_warning "Group '$group' does not exist, skipping"
            fi
        done
    fi
    
    # Add to state
    local user_config="{\"shell_access\": $allow_shell, \"home_dataset\": \"$pool/homes/$username\", \"groups\": $groups_array, \"created\": \"$(date -Iseconds)\"}"
    add_to_state_object "users" "$username" "$user_config"
}

# Create user
cmd_create_user() {
    local username="$1"
    local shell_opt="$2"
    
    check_initialized
    
    if [[ -z "$username" ]]; then
        print_error "Username is required"
        exit 1
    fi
    
    # Validate username
    if ! [[ "$username" =~ ^[a-zA-Z0-9._-]+$ ]]; then
        print_error "Username contains invalid characters"
        exit 1
    fi
    
    # Check if user already exists
    local state
    state=$(read_state)
    if echo "$state" | jq -e ".users[\"$username\"]" &>/dev/null; then
        print_error "User '$username' already managed by this tool"
        exit 1
    fi
    
    if id "$username" &>/dev/null; then
        print_error "System user '$username' already exists"
        exit 1
    fi
    
    local allow_shell="false"
    if [[ "$shell_opt" == "--shell" ]]; then
        allow_shell="true"
    fi
    
    local pool
    pool=$(get_state_value "zfs_pool" "")
    
    # Check if home directory already exists and get actual mountpoint
    local actual_mountpoint
    actual_mountpoint=$(zfs get -H -o value mountpoint "$pool/homes/$username" 2>/dev/null)
    if [[ $? -eq 0 ]]; then
        print_warning "ZFS dataset $pool/homes/$username already exists at $actual_mountpoint"
        echo "Do you want to continue? (y/N):"
        read -r continue_choice
        if [[ "$continue_choice" != "y" && "$continue_choice" != "Y" ]]; then
            print_info "Operation cancelled"
            exit 0
        fi
    fi
    
    print_info
    echo "Shell access: $allow_shell"
    echo "Home directory: /$pool/homes/$username"
    echo ""
    
    password=$(get_passwd)
    
    # Show available groups from state and validate selection
    echo ""
    echo "Available groups:"
    local available_groups
    available_groups=$(get_state_object_keys "groups")
    if [[ -z "$available_groups" ]]; then
        print_warning "No groups defined in state"
    else
        echo "$available_groups" | while read -r group; do
            echo " - $group"
        done
    fi
    echo ""
    echo "Add user to additional groups? (comma-separated, or Enter to skip):"
    read -r additional_groups
    
    # Validate groups against state
    if [[ -n "$additional_groups" ]]; then
        IFS=',' read -ra group_list <<< "$additional_groups"
        for group in "${group_list[@]}"; do
            group=$(echo "$group" | xargs) # trim whitespace
            if [[ -n "$available_groups" ]] && ! echo "$available_groups" | grep -q "^$group$"; then
                print_error "Group '$group' not found in state"
                exit 1
            fi
        done
    fi
    
    # Execute business logic
    create_user_business_logic "$username" "$allow_shell" "$password" "$additional_groups"
    
    print_info "User '$username' created successfully!"
    echo "Access via: \\\\$(hostname)\\$username"
}   