# Change password
cmd_passwd() {
    local username="$1"
    local current_user
    current_user=$(whoami)

    # If no username provided, use current user
    if [[ -z "$username" ]]; then
        username="$current_user"

        # Check if current user is managed by this tool
        if [[ -f "$STATE_FILE" ]]; then
            local state
            state=$(read_state)
            if ! echo "$state" | jq -e ".users[\"$username\"]" &>/dev/null; then
                print_error "Current user '$username' is not managed by this tool"
                exit 1
            fi
        else
            print_error "System not initialized"
            exit 1
        fi
    else
        # If username provided, must be root
        if [[ $EUID -ne 0 ]]; then
            print_error "Root privileges required to change another user's password"
            exit 1
        fi

        check_initialized

        # Check if user exists in state
        local state
        state=$(read_state)
        if ! echo "$state" | jq -e ".users[\"$username\"]" &>/dev/null; then
            print_error "User '$username' is not managed by this tool"
            exit 1
        fi
    fi

    print_info "Changing password for user: $username"

    password=$(get_passwd)

    # Check if user has shell access
    local state
    state=$(read_state)
    local shell_access
    shell_access=$(echo "$state" | jq -r ".users[\"$username\"].shell_access")

    # Update system password if shell access enabled
    if [[ "$shell_access" == "true" ]]; then
        print_info "Updating system password..."
        echo "$username:$new_password" | chpasswd
    fi

    # Update Samba password
    print_info "Updating Samba password..."
    (echo "$new_password"; echo "$new_password") | smbpasswd -a -s "$username"

    print_info "Password changed successfully for user '$username'!"
}
