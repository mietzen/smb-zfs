
# Initialize state file
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
}

# Read state
read_state() {
    if [[ -f "$STATE_FILE" ]]; then
        cat "$STATE_FILE"
    else
        echo "{}"
    fi
}

# Write state
write_state() {
    local state="$1"
    echo "$state" > "$STATE_FILE"
    chmod 600 "$STATE_FILE"
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
    state=$(echo "$state" | jq ".$key = \"$value\"")
    write_state "$state"
}

# Add to state object
add_to_state_object() {
    local object="$1"
    local key="$2"
    local value="$3"
    local state
    state=$(read_state)
    state=$(echo "$state" | jq ".$object[\"$key\"] = $value")
    write_state "$state"
}

# Remove from state object
remove_from_state_object() {
    local object="$1"
    local key="$2"
    local state
    state=$(read_state)
    state=$(echo "$state" | jq "del(.$object[\"$key\"])")
    write_state "$state"
}

# Get state object keys
get_state_object_keys() {
    local object="$1"
    local state
    state=$(read_state)
    echo "$state" | jq -r ".$object | keys[]" 2>/dev/null || true
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
