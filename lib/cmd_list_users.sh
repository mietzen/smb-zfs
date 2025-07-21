# List users
# TODO: Check if all escaping in jq is needed
cmd_list_users() {
    check_initialized

    print_info "Users managed by $SCRIPT_NAME"

    local state
    state=$(read_state)

    if ! echo "$state" | jq -e '.users | keys | length > 0' &>/dev/null; then
        echo "No users created yet."
        return
    fi

    echo "$state" | jq -r '.users | to_entries[] | "\(.key):\n  Shell access: \(.value.shell_access)\n  Home dataset: \(.value.home_dataset)\n  Groups: \(.value.groups | join(", "))\n  Created: \(.value.created)\n"'
}
