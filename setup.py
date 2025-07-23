#!/usr/bin/env python

from setuptools import setup

setup(
    data_files=[
        (
            '/usr/share/bash-completion/completions',
            [
                'completion/smb-zfs-completion.sh',
                'completion/smb-zfs-wizard-completion.sh'
            ]
        )
    ]
)
