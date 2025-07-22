import os
import shutil
import re
from datetime import datetime

from . import SMB_CONF, AVAHI_SMB_SERVICE


class ConfigGenerator:
    def _backup_file(self, file_path):
        if os.path.exists(file_path):
            backup_path = (
                f"{file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            shutil.copy(file_path, backup_path)

    def create_smb_conf(self, pool, server_name, workgroup, macos_optimized):
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
            content += """
    vfs objects = fruit streams_xattr
    fruit:metadata = stream
    fruit:model = MacSamba
    fruit:posix_rename = yes
    fruit:veto_appledouble = no
    fruit:wipe_intentionally_left_blank_rfork = yes
    fruit:delete_empty_adfiles = yes
"""
        content += f"""
[homes]
    comment = Home Directories
    path = /{pool}/homes/%S
    browseable = no
    read only = no
    create mask = 0700
    directory mask = 0700
    valid users = %S
    force user = %S
"""
        with open(SMB_CONF, "w") as f:
            f.write(content)

    def create_avahi_conf(self):
        self._backup_file(AVAHI_SMB_SERVICE)
        content = """
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
        os.makedirs(os.path.dirname(AVAHI_SMB_SERVICE), exist_ok=True)
        with open(AVAHI_SMB_SERVICE, "w") as f:
            f.write(content)

    def add_share_to_conf(self, share_data):
        with open(SMB_CONF, "a") as f:
            f.write(f"""
[{share_data["name"]}]
    comment = {share_data["comment"]}
    path = {share_data["path"]}
    browseable = {"yes" if share_data["browseable"] else "no"}
    read only = {"yes" if share_data["read_only"] else "no"}
    create mask = 0664
    directory mask = 0775
    valid users = {share_data["valid_users"]}
    force user = {share_data["owner"]}
    force group = {share_data["group"]}
""")

    def remove_share_from_conf(self, share_name):
        self._backup_file(SMB_CONF)
        with open(SMB_CONF, "r") as f:
            lines = f.readlines()

        share_pattern = re.compile(r"^\s*\[{}\]\s*$".format(re.escape(share_name)))
        section_pattern = re.compile(r"^\s*\[.*\]\s*$")

        in_section = False
        with open(SMB_CONF, "w") as f:
            for line in lines:
                if share_pattern.match(line):
                    in_section = True
                    continue
                if in_section and section_pattern.match(line):
                    in_section = False

                if not in_section:
                    f.write(line)
