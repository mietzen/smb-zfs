# Modify group
cmd_modify_group() {
    local groupname="$1"

    check_initialized

    if [[ -z "$groupname" ]]; then
        print_error "Group name is required"
        exit 1
    fi

    # Check if group exists in state
    local state
    state=$(read_state)
    if ! echo "$state" | jq -e ".groups[\"$groupname\"]" &>/dev/null; then
        print_error "Group '$groupname' is not managed by this tool"
        exit 1
    fi

    print_header "MODIFY GROUP" "Modifying group: $groupname"

    # Get current members
    local current_members
    current_members=$(echo "$state" | jq -r ".groups[\"$groupname\"].members | join(\", \")")

    echo "Current members: $current_members"
    echo ""
    echo "Available users:"
    get_state_object_keys "users" | while read -r user; do
        echo "  - $user"
    done
    echo ""

    echo "Add users to group (comma-separated):"
    read -r users_to_add

    echo "Remove users from group (comma-separated):"
    read -r users_to_remove

    local members_array
    members_array=$(echo "$state" | jq -r ".groups[\"$groupname\"].members")

    # Add users
    if [[ -n "$users_to_add" ]]; then
        IFS=',' read -ra user_list <<< "$users_to_add"
        for user in "${user_list[@]}"; do
            user=$(echo "$user" | xargs) # trim whitespace
            if id "$user" &>/dev/null; then
                usermod -a -G "$groupname" "$user"
                if ! echo "$members_array" | jq -e ". | index(\"$user\")" &>/dev/null; then
                    members_array=$(echo "$members_array" | jq ". + [\"$user\"]")
                fi
                print_status "Added user '$user' to group '$groupname'"
            else
                print_warning "User '$user' does not exist, skipping"
            fi
        done
    fi

    # Remove users
    if [[ -n "$users_to_remove" ]]; then
        IFS=',' read -ra user_list <<< "$users_to_remove"
        for user in "${user_list[@]}"; do
            user=$(echo "$user" | xargs) # trim whitespace
            if id "$user" &>/dev/null; then
                gpasswd -d "$user" "$groupname" 2>/dev/null || true
                members_array=$(echo "$members_array" | jq "map(select(. != \"$user\"))")
                print_status "Removed user '$user' from group '$groupname'"
            else
                print_warning "User '$user' does not exist, skipping"
            fi
        done
    fi

    # Update state
    local updated_config
    updated_config=$(echo "$state" | jq --argjson members "$members_array" ".groups[\"$groupname\"].members = \$members")
    write_state "$updated_config"

    print_status "Group '$groupname' modified successfully!"
}
