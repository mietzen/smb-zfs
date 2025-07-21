# Create SMB configuration
create_smb_conf() {
    local pool="$1"
    local server_name="$2"
    local workgroup="$3"
    local macos_optimized="$4"

    cat > "$SMB_CONF" << EOF
# Samba configuration file created by $SCRIPT_NAME
# $(date)

[global]
    # Basic server settings
    workgroup = $workgroup
    server string = $server_name Samba Server
    netbios name = $server_name

    # Security settings
    security = user
    map to guest = never
    passdb backend = tdbsam

    # Network settings
    dns proxy = no

    # Logging
    log file = /var/log/samba/log.%m
    max log size = 1000
    log level = 1

    # Performance
    socket options = TCP_NODELAY IPTOS_LOWDELAY SO_RCVBUF=524288 SO_SNDBUF=524288

    # Avahi/Zeroconf support
    multicast dns register = yes

    # File creation settings
    create mask = 0664
    directory mask = 0775
    force create mode = 0664
    force directory mode = 0775
EOF

    if [[ "$macos_optimized" == "true" ]]; then
        cat >> "$SMB_CONF" << EOF

    # Mac compatibility with vfs_fruit
    vfs objects = fruit streams_xattr
    fruit:metadata = stream
    fruit:model = MacSamba
    fruit:posix_rename = yes
    fruit:veto_appledouble = no
    fruit:wipe_intentionally_left_blank_rfork = yes
    fruit:delete_empty_adfiles = yes
EOF
    fi

    cat >> "$SMB_CONF" << EOF

# User home directories
[homes]
    comment = Home Directories
    path = /$pool/homes/%S
    browseable = no
    read only = no
    create mask = 0700
    directory mask = 0700
    valid users = %S
    force user = %S

# Shared directory
[shared]
    comment = Shared Files
    path = /$pool/shared
    browseable = yes
    read only = no
    create mask = 0664
    directory mask = 0775
    valid users = @smb_users
EOF
}
