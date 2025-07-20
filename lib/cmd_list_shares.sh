# List shares
cmd_list_shares() {
    check_initialized

    print_header "SHARES" "Shares managed by $SCRIPT_NAME"

    local state
    state=$(read_state)

    if ! echo "$state" | jq -e '.shares | keys | length > 0' &>/dev/null; then
        echo "No shares created yet."
        return
    fi

    echo "$state" | jq -r '.shares | to_entries[] | "\(.key):\n  Path: \(.value.path)\n  Comment: \(.value.comment)\n  Owner: \(.value.owner):\(.value.group)\n  Permissions: \(.value.permissions)\n  Valid users: \(.value.valid_users)\n  Read-only: \(.value.read_only)\n  Browseable: \(.value.browseable)\n  Created: \(.value.created)\n"'
}
