# Create user
# TODO: Extract the business logic from the guided cli prompts, for reuse in other intefaces, into a seperate bash function.
# TODO: Check if all escaping in jq is needed
# TODO: Use zfs get mountpoint to determine actual path, if home already exists, also print_warning and prompt if you want to continue
# TODO: Show available groups from state, fail if group not in state
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

    print_info
    echo "Shell access: $allow_shell"
    echo "Home directory: /$pool/homes/$username"
    echo ""

    password=$(get_passwd)

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

    # Prompt for additional groups
    echo ""
    echo "Available groups:"
    get_state_object_keys "groups" | while read -r group; do
        echo "  - $group"
    done
    echo ""
    echo "Add user to additional groups? (comma-separated, or Enter to skip):"
    read -r additional_groups

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

    print_info "User '$username' created successfully!"
    echo "Access via: \\\\$(hostname)\\$username"
}