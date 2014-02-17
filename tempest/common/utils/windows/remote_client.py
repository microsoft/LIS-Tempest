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
         #                             ca_trust_path='winrm_client_cert.pem')

            shell_id = p.open_shell()

            command_id = p.run_command(shell_id, cmd)
            std_out, std_err, status_code = p.get_command_output(shell_id, command_id)

            p.cleanup_command(shell_id, command_id)
            p.close_shell(shell_id)
            #print std_err
            return (std_out, std_err, status_code)
        except Exception, e:
            print e
            sys.exit()
        else:
            pass
        finally:
            pass
           # return (std_out, std_err, status_code)



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

if __name__ == "__main__":
    #cmd = 'powershell -Command Get-NetIPConfiguration'
    #hostname = '10.7.13.72'
    hostname = '10.7.1.247'
    username = 'Administrator'
    password = 'Passw0rd'
    script = 'AddHardDiskPass.ps1'
    hvServer ='OLISA-2012R2'
    vmName = 'instance-00000046'
    cmd1 = 'powershell Get-VMIntegrationService -ComputerName ' + hvServer +' -VMName '+  vmName +' -Name Shutdown'
    print cmd1
    cmd2 = 'powershell Disable-VMIntegrationService -ComputerName ' + hvServer +' -VMName '+  vmName +' -Name Shutdown'
    cmd3 = 'powershell Enable-VMIntegrationService -ComputerName ' + hvServer +' -VMName '+  vmName +' -Name Shutdown'

    wsmancmd = WinRemoteClient(hostname, username, password)
  #  wsmancmd.copy_file(script)
    #wsmancmd.run_wsman_cmd('powershell ' + script)
    #std_out, std_err, exit_code = wsmancmd.run_wsman_cmd('powershell pwd')
    print cmd1
    std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd1)
    sys.stdout.write(std_out)
    sys.stderr.write(std_err)

    print cmd2
    std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd2)
    sys.stdout.write(std_out)
    sys.stderr.write(std_err)

    print cmd1
    std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd1)
    sys.stdout.write(std_out)
    sys.stderr.write(std_err)

    print cmd3
    std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd3)
    sys.stdout.write(std_out)
    sys.stderr.write(std_err)

    print cmd1
    std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd1)
    sys.stdout.write(std_out)
    sys.stderr.write(std_err)



    # sys.stdout.write(std_out)
    # sys.stderr.write(std_err)
