# Create group
cmd_create_group() {
    local groupname="$1"

    check_initialized

    if [[ -z "$groupname" ]]; then
        print_error "Group name is required"
        exit 1
    fi

    # Validate group name
    if ! [[ "$groupname" =~ ^[a-zA-Z0-9._-]+$ ]]; then
        print_error "Group name contains invalid characters"
        exit 1
    fi

    # Check if group already exists
    local state
    state=$(read_state)
    if echo "$state" | jq -e ".groups[\"$groupname\"]" &>/dev/null; then
        print_error "Group '$groupname' already managed by this tool"
        exit 1
    fi

    if getent group "$groupname" &>/dev/null; then
        print_error "System group '$groupname' already exists"
        exit 1
    fi

    print_header "CREATE GROUP" "Creating group: $groupname"

    echo "Enter group description [default: $groupname Group]:"
    read -r description
    if [[ -z "$description" ]]; then
        description="$groupname Group"
    fi

    # Create system group
    print_status "Creating system group..."
    groupadd "$groupname"

    # Show available users
    echo ""
    echo "Available users:"
    get_state_object_keys "users" | while read -r user; do
        echo "  - $user"
    done
    echo ""
    echo "Add users to group? (comma-separated, or Enter to skip):"
    read -r users_to_add

    local members_array="[]"
    if [[ -n "$users_to_add" ]]; then
        IFS=',' read -ra user_list <<< "$users_to_add"
        for user in "${user_list[@]}"; do
            user=$(echo "$user" | xargs) # trim whitespace
            if id "$user" &>/dev/null; then
                usermod -a -G "$groupname" "$user"
                members_array=$(echo "$members_array" | jq ". + [\"$user\"]")
                print_status "Added user '$user' to group '$groupname'"
            else
                print_warning "User '$user' does not exist, skipping"
            fi
        done
    fi

    # Add to state
    local group_config="{\"description\": \"$description\", \"members\": $members_array, \"created\": \"$(date -Iseconds)\"}"
    add_to_state_object "groups" "$groupname" "$group_config"

    print_status "Group '$groupname' created successfully!"
}
