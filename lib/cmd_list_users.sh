# List users business logic function
list_users_business_logic() {
    check_initialized

    local state
    state=$(read_state)

    if ! echo "$state" | jq -e '.users | keys | length > 0' &>/dev/null; then
        return 1  # No users found
    fi

    echo "$state" | jq -r '.users | to_entries[] | "\(.key):\n Shell access: \(.value.shell_access)\n Home dataset: \(.value.home_dataset)\n Groups: \(.value.groups | join(", "))\n Created: \(.value.created)\n"'
    return 0
}

# List users
cmd_list_users() {
    print_info "Users managed by $SCRIPT_NAME"

    if ! list_users_business_logic; then
        echo "No users created yet."
    fi
}