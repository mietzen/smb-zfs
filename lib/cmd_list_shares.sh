# List shares business logic function
list_shares_business_logic() {
    check_initialized

    local state
    state=$(read_state)

    if ! echo "$state" | jq -e '.shares | keys | length > 0' &>/dev/null; then
        return 1  # No shares found
    fi

    echo "$state" | jq -r '.shares | to_entries[] | "\(.key):\n Path: \(.value.path)\n Comment: \(.value.comment)\n Owner: \(.value.owner):\(.value.group)\n Permissions: \(.value.permissions)\n Valid users: \(.value.valid_users)\n Read-only: \(.value.read_only)\n Browseable: \(.value.browseable)\n Created: \(.value.created)\n"'
    return 0
}

# List shares
cmd_list_shares() {
    print_info "Shares managed by $SCRIPT_NAME"

    if ! list_shares_business_logic; then
        echo "No shares created yet."
    fi
}