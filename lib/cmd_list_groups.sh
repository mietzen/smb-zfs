# List groups business logic function
list_groups_business_logic() {
    check_initialized

    local state
    state=$(read_state)

    if ! echo "$state" | jq -e '.groups | keys | length > 0' &>/dev/null; then
        return 1  # No groups found
    fi

    echo "$state" | jq -r '.groups | to_entries[] | "\(.key):\n Description: \(.value.description)\n Members: \(.value.members | join(", "))\n Created: \(.value.created)\n"'
    return 0
}

# List groups
cmd_list_groups() {
    print_info "Groups managed by $SCRIPT_NAME"

    if ! list_groups_business_logic; then
        echo "No groups created yet."
    fi
}