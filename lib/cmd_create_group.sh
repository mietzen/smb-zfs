# Create group
# TODO: Extract the business logic from the guided cli prompts, for reuse in other intefaces, into a seperate bash function.
# TODO: Check if all escaping in jq is needed
# TODO: Dont use pos args for user handover prompt for them
# TODO: Show available users from state, fail if user not in state
cmd_create_group() {
    local groupname="$1"
    shift

    local description=""
    local users_to_add=()

    # Parse remaining arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --description)
                description="$2"
                shift 2
                ;;
            --desc)
                description="$2"
                shift 2
                ;;
            *)
                # Treat remaining arguments as users to add
                users_to_add+=("$1")
                shift
                ;;
        esac
    done

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

    # Set default description if not provided
    if [[ -z "$description" ]]; then
        description="$groupname Group"
    fi

    print_info "Creating group: $groupname"

    # Create system group
    print_info "Creating system group..."
    groupadd "$groupname"

    local members_array="[]"

    # Add users to group if specified
    if [[ ${#users_to_add[@]} -gt 0 ]]; then
        for user in "${users_to_add[@]}"; do
            user=$(echo "$user" | xargs) # trim whitespace
            if id "$user" &>/dev/null; then
                usermod -a -G "$groupname" "$user"
                members_array=$(echo "$members_array" | jq ". + [\"$user\"]")
                print_info "Added user '$user' to group '$groupname'"
            else
                print_warning "User '$user' does not exist, skipping"
            fi
        done
    fi

    # Add to state
    local group_config="{\"description\": \"$description\", \"members\": $members_array, \"created\": \"$(date -Iseconds)\"}"
    add_to_state_object "groups" "$groupname" "$group_config"

    print_info "Group '$groupname' created successfully!"
}