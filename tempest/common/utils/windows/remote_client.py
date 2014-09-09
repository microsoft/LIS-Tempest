#!/usr/bin/python

# Copyright 2014 Cloudbase Solutions Srl
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import getopt
import sys

from winrm import protocol

class WinRemoteClient(object):

    def __init__(self, hostname, username, password):

        self.hostname = 'https://' + hostname + ':5986/wsman';
        self.username = username;
        self.password = password;

    def run_wsman_cmd(self, cmd):
        protocol.Protocol.DEFAULT_TIMEOUT = "PT3600S"
        try:
            p = protocol.Protocol(endpoint=self.hostname,
                                      transport='plaintext',
                                      username=self.username,
                                      password=self.password)

            shell_id = p.open_shell()

            command_id = p.run_command(shell_id,cmd)
            std_out, std_err, status_code = p.get_command_output(shell_id, command_id)

            p.cleanup_command(shell_id, command_id)
            p.close_shell(shell_id)

            return (std_out, std_err, status_code)

        except Exception as exc:
            raise exc

    def run_wsman_script(self, script):
        protocol.Protocol.DEFAULT_TIMEOUT = "PT3600S"

        p = protocol.Protocol(endpoint=self.hostname,
                              transport='plaintext',
                              username=self.username,
                              password=self.password)

        shell_id = p.open_shell()

        command_id = p.run_command(shell_id, cmd)
        std_out, std_err, status_code = p.get_command_output(shell_id, command_id)

        p.cleanup_command(shell_id, command_id)
        p.close_shell(shell_id)

        return (std_out, std_err, status_code)

    def copy_file(self, file):

        """ Not YET Implemented"""

        std_out, std_err, exit_code = wsmancmd.run_wsman_cmd('powershell New-Item c:\\scripts\\' + script + ' -type file')
        if std_out:
            print std_out
        if std_err:
            print std_err

        with open(script) as f:
            for line in f:
                std_out, std_err, exit_code = wsmancmd.run_wsman_cmd('')
                wsmancmd.run_wsman_cmd('')
