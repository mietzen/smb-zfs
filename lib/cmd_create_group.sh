# Create group business logic function
create_group_business_logic() {
    local groupname="$1"
    local description="$2"
    local -n users_to_add_ref="$3"  # nameref to array
    
    check_initialized
    
    # Validate group name
    if ! [[ "$groupname" =~ ^[a-zA-Z0-9._-]+$ ]]; then
        print_error "Group name contains invalid characters"
        return 1
    fi
    
    # Check if group already exists
    local state
    state=$(read_state)
    if echo "$state" | jq -e ".groups[\"$groupname\"]" &>/dev/null; then
        print_error "Group '$groupname' already managed by this tool"
        return 1
    fi
    
    if getent group "$groupname" &>/dev/null; then
        print_error "System group '$groupname' already exists"
        return 1
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
    if [[ ${#users_to_add_ref[@]} -gt 0 ]]; then
        # Show available users from state
        local available_users
        available_users=$(echo "$state" | jq -r '.users | keys[]' 2>/dev/null || echo "")
        if [[ -n "$available_users" ]]; then
            print_info "Available users in state: $(echo "$available_users" | tr '\n' ' ')"
        fi
        
        for user in "${users_to_add_ref[@]}"; do
            user=$(echo "$user" | xargs) # trim whitespace
            
            # Check if user exists in state
            if ! echo "$state" | jq -e ".users[\"$user\"]" &>/dev/null; then
                print_error "User '$user' not found in state, skipping"
                continue
            fi
            
            if id "$user" &>/dev/null; then
                usermod -a -G "$groupname" "$user"
                members_array=$(echo "$members_array" | jq ". + [\"$user\"]")
                print_info "Added user '$user' to group '$groupname'"
            else
                print_warning "User '$user' does not exist on system, skipping"
            fi
        done
    fi
    
    # Add to state
    local group_config="{\"description\": \"$description\", \"members\": $members_array, \"created\": \"$(date -Iseconds)\"}"
    add_to_state_object "groups" "$groupname" "$group_config"
    
    print_info "Group '$groupname' created successfully!"
    return 0
}

# Create group
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
    
    if [[ -z "$groupname" ]]; then
        print_error "Group name is required"
        exit 1
    fi
    
    # Call business logic function
    create_group_business_logic "$groupname" "$description" users_to_add
}