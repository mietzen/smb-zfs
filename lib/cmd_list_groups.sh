# List groups
# TODO: Check if all escaping in jq is needed
cmd_list_groups() {
    check_initialized

    print_info "Groups managed by $SCRIPT_NAME"

    local state
    state=$(read_state)

    if ! echo "$state" | jq -e '.groups | keys | length > 0' &>/dev/null; then
        echo "No groups created yet."
        return
    fi

    echo "$state" | jq -r '.groups | to_entries[] | "\(.key):\n  Description: \(.value.description)\n  Members: \(.value.members | join(", "))\n  Created: \(.value.created)\n"'
}
