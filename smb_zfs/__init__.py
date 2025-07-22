from .zfs import ZFS
from .system import System
from .state_manager import StateManager
from .config_generator import ConfigGenerator
from .smb_zfs import SmbZfsManager

STATE_FILE = "/etc/smb-zfs.state"
SMB_CONF = "/etc/samba/smb.conf"
AVAHI_SMB_SERVICE = "/etc/avahi/services/smb.service"
VERSION = "0.1.0"

class SmbZfsError(Exception):
    """Custom exception for smb-zfs errors."""
    pass
