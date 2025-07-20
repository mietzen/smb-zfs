# Utilities

# Backup file
backup_file() {
    local file="$1"
    if [[ -f "$file" ]]; then
        cp "$file" "$file.backup.$(date +%Y%m%d_%H%M%S)"
        print_info "Backed up $file"
    fi
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root"
        exit 1
    fi
}

get_passwd() {
    # Get password with validation
    local password password_confirm

    while true; do
        read -r -s -p "Enter password for user '$username': " password
        echo ""
        read -r -s -p "Confirm password: " password_confirm
        echo ""

        # Check if passwords match
        if [[ "$password" != "$password_confirm" ]]; then
            print_error "Passwords do not match"
            continue
        fi

        # Empty check
        if [[ -z "$password" ]]; then
            print_error "Password cannot be empty"
            continue
        fi

        # Length check
        if [[ ${#password} -lt 8 ]]; then
            print_error "Password must be at least 8 characters long"
            continue
        fi

        # Check for at least one number
        if ! [[ "$password" =~ [0-9] ]]; then
            print_error "Password must contain at least one number"
            continue
        fi

        # Check for at least one special character (recommended but optional for compatibility)
        # smbpasswd and some PAM modules may have special character restrictions
        if ! [[ "$password" =~ [^a-zA-Z0-9] ]]; then
            print_error "Password must contain at least one special character"
            continue
        fi

        # Check for whitespace characters
        if [[ "$password" =~ [[:space:]] ]]; then
            print_error "Password cannot contain spaces or whitespace characters"
            continue
        fi

        # Check for control characters (ASCII 0-31, 127)
        if [[ "$password" =~ $'\001'|$'\002'|$'\003'|$'\004'|$'\005'|$'\006'|$'\007'|$'\010'|$'\011'|$'\012'|$'\013'|$'\014'|$'\015'|$'\016'|$'\017'|$'\020'|$'\021'|$'\022'|$'\023'|$'\024'|$'\025'|$'\026'|$'\027'|$'\030'|$'\031'|$'\032'|$'\033'|$'\034'|$'\035'|$'\036'|$'\037'|$'\177' ]]; then
            print_error "Password cannot contain control characters"
            continue
        fi

        # All validations passed
        break
    done

    echo "$password"
}

# Print functions
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_warning() {
    print_msg YELLOW WARNING $1
}

print_error() {
    print_msg RED ERROR $1
}

print_info() {
    print_msg BLUE INFO $2
}

print_msg() {
    local color="$1"
    local label="$2"
    shift 2
    echo -e "${!color}[$label]${NC} $*"
}
