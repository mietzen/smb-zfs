# Initialize state file
# Creates backup when writing state and validates JSON format
init_state() {
    if [[ ! -f "$STATE_FILE" ]]; then
        cat > "$STATE_FILE" << 'EOF'
{
  "version": "1.0",
  "initialized": false,
  "zfs_pool": "",
  "server_name": "",
  "workgroup": "",
  "macos_optimized": false,
  "users": {},
  "shares": {},
  "groups": {}
}
EOF
        print_info "Initialized state file: $STATE_FILE"
    fi

    # Validate JSON format
    if ! jq '.' "$STATE_FILE" >/dev/null 2>&1; then
        print_error "Invalid JSON in state file: $STATE_FILE"
        return 1
    fi
}

# Read state
read_state() {
    if [[ -f "$STATE_FILE" ]]; then
        cat "$STATE_FILE"
    else
        echo "{}"
    fi
}

# Write state with backup
write_state() {
    local state="$1"

    # Validate JSON before writing
    if ! echo "$state" | jq '.' >/dev/null 2>&1; then
        print_error "Invalid JSON provided to write_state"
        return 1
    fi

    # Create backup if state file exists
    if [[ -f "$STATE_FILE" ]]; then
        cp "$STATE_FILE" "${STATE_FILE}.backup"
    fi

    # Write new state
    echo "$state" > "$STATE_FILE"
    chmod 600 "$STATE_FILE"

    # Validate written file
    if ! jq '.' "$STATE_FILE" >/dev/null 2>&1; then
        print_error "Failed to write valid JSON to state file"
        # Restore backup if available
        if [[ -f "${STATE_FILE}.backup" ]]; then
            mv "${STATE_FILE}.backup" "$STATE_FILE"
            print_info "Restored state file from backup"
        fi
        return 1
    fi
}

# Get state value using jq
get_state_value() {
    local key="$1"
    local default="$2"
    local state
    state=$(read_state)
    echo "$state" | jq -r ".$key // \"$default\""
}

# Set state value using jq
set_state_value() {
    local key="$1"
    local value="$2"
    local state
    state=$(read_state)
    state=$(echo "$state" | jq --arg k "$key" --arg v "$value" '.[$k] = $v')
    write_state "$state"
}

# Add to state object
add_to_state_object() {
    local object="$1"
    local key="$2"
    local value="$3"
    local state
    state=$(read_state)
    state=$(echo "$state" | jq --arg obj "$object" --arg k "$key" --argjson v "$value" '.[$obj][$k] = $v')
    write_state "$state"
}

# Remove from state object
remove_from_state_object() {
    local object="$1"
    local key="$2"
    local state
    state=$(read_state)
    state=$(echo "$state" | jq --arg obj "$object" --arg k "$key" 'del(.[$obj][$k])')
    write_state "$state"
}

# Get state object keys
get_state_object_keys() {
    local object="$1"
    local state
    state=$(read_state)
    echo "$state" | jq --arg obj "$object" -r '.[$obj] | keys[]' 2>/dev/null || true
}

# Check if initialized
check_initialized() {
    local initialized
    initialized=$(get_state_value "initialized" "false")
    if [[ "$initialized" != "true" ]]; then
        print_error "System not initialized. Run '$SCRIPT_NAME install <POOL>' first."
        exit 1
    fi
}