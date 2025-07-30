import os
import re
import shutil
import logging
from datetime import datetime
from typing import Dict, Any

from .const import SMB_CONF, AVAHI_SMB_SERVICE

# --- Logger Setup ---
logger = logging.getLogger(__name__)

# --- Constants ---
MACOS_SETTINGS = """
    vfs objects = fruit streams_xattr
    fruit:metadata = stream
    fruit:model = MacSamba
    fruit:posix_rename = yes
    fruit:veto_appledouble = no
    fruit:wipe_intentionally_left_blank_rfork = yes
    fruit:delete_empty_adfiles = yes
"""

AVAHI_CONF = """
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">%h</name>
  <service>
    <type>_smb._tcp</type>
    <port>445</port>
  </service>
  <service>
    <type>_device-info._tcp</type>
    <port>0</port>
    <txt-record>model=RackMac</txt-record>
  </service>
</service-group>
"""


class ConfigGenerator:
    """Handles the creation and modification of configuration files."""

    def _backup_file(self, file_path: str) -> None:
        """Creates a timestamped backup and an initial backup if one doesn't exist."""
        if os.path.exists(file_path):
            init_backup_path = f"{file_path}.backup.init"
            if not os.path.exists(init_backup_path):
                logger.info("Creating initial backup for %s at %s", file_path, init_backup_path)
                shutil.copy(file_path, init_backup_path)
            
            backup_path = f"{file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.debug("Creating timestamped backup for %s at %s", file_path, backup_path)
            shutil.copy(file_path, backup_path)

    def restore_initial_state(self, file_path: str) -> bool:
        """Restores a file from its initial backup if it exists."""
        init_backup_path = f"{file_path}.backup.init"
        if os.path.exists(init_backup_path):
            logger.warning("Restoring initial state for %s from %s", file_path, init_backup_path)
            shutil.copy(init_backup_path, file_path)
            return True
        else:
            logger.warning("Initial backup for %s not found. Cannot restore.", file_path)
            return False

    def create_smb_conf(self, primary_pool: str, server_name: str, workgroup: str, macos_optimized: bool) -> None:
        """Creates the main smb.conf file from scratch."""
        logger.info("Generating new smb.conf file.")
        self._backup_file(SMB_CONF)
        content = f"""
[global]
    workgroup = {workgroup.upper()}
    server string = {server_name} Samba Server
    netbios name = {server_name}
    security = user
    map to guest = never
    passdb backend = tdbsam
    dns proxy = no
    log file = /var/log/samba/log.%m
    max log size = 1000
    log level = 1
    socket options = TCP_NODELAY IPTOS_LOWDELAY SO_RCVBUF=524288 SO_SNDBUF=524288
    multicast dns register = yes
    create mask = 0664
    directory mask = 0775
    force create mode = 0664
    force directory mode = 0775
"""
        if macos_optimized:
            logger.debug("Adding macOS specific settings to smb.conf.")
            content += MACOS_SETTINGS
        
        content += f"""
[homes]
    comment = Home Directories
    path = /{primary_pool}/homes/%S
    browseable = no
    read only = no
    create mask = 0700
    directory mask = 0700
    valid users = %S
    force user = %S
"""
        logger.debug("Writing generated content to %s.", SMB_CONF)
        with open(SMB_CONF, "w") as f:
            f.write(content)

    def create_avahi_conf(self) -> None:
        """Creates the Avahi service file for Samba."""
        logger.info("Generating new Avahi service file for Samba.")
        self._backup_file(AVAHI_SMB_SERVICE)
        os.makedirs(os.path.dirname(AVAHI_SMB_SERVICE), exist_ok=True)
        logger.debug("Writing Avahi configuration to %s.", AVAHI_SMB_SERVICE)
        with open(AVAHI_SMB_SERVICE, "w") as f:
            f.write(AVAHI_CONF)

    def add_share_to_conf(self, share_name: str, share_data: Dict[str, Any]) -> None:
        """Appends a new share section to the smb.conf file."""
        logger.info("Adding share '%s' to smb.conf.", share_name)
        with open(SMB_CONF, "a") as f:
            f.write(f"""
[{share_name}]
    comment = {share_data['smb_config']["comment"]}
    path = {share_data['dataset']["mount_point"]}
    browseable = {"yes" if share_data['smb_config']["browseable"] else "no"}
    read only = {"yes" if share_data['smb_config']["read_only"] else "no"}
    create mask = 0664
    directory mask = 0775
    valid users = {share_data['smb_config']["valid_users"]}
    force user = {share_data['system']["owner"]}
    force group = {share_data['system']["group"]}
""")
        logger.debug("Share '%s' appended to configuration.", share_name)

    def remove_share_from_conf(self, share_name: str) -> None:
        """Removes a share section from the smb.conf file."""
        logger.info("Removing share '%s' from smb.conf.", share_name)
        self._backup_file(SMB_CONF)
        try:
            with open(SMB_CONF, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            logger.warning("smb.conf not found, cannot remove share '%s'.", share_name)
            return

        share_pattern = re.compile(
            r"^\s*\[{}\]\s*$".format(re.escape(share_name)))
        section_pattern = re.compile(r"^\s*\[.*\]\s*$")

        in_section = False
        with open(SMB_CONF, "w") as f:
            for line in lines:
                if share_pattern.match(line):
                    in_section = True
                    logger.debug("Found start of section for share '%s'.", share_name)
                    continue
                if in_section and section_pattern.match(line):
                    in_section = False
                    logger.debug("Found end of section for share '%s'.", share_name)

                if not in_section:
                    f.write(line)
        logger.info("Finished processing smb.conf for removal of share '%s'.", share_name)
