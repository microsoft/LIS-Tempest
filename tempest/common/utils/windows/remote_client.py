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


from oslo_log import log
from winrm import protocol


LOG = log.getLogger(__name__)
SUCCESS_RETURN_CODE = 0


class WinRemoteClient(object):

    def __init__(self, hostname, username, password):

        self.hostname = 'https://' + hostname + ':5986/wsman'
        self.username = username
        self.password = password

    def run_wsman_cmd(self, cmd):
        protocol.Protocol.DEFAULT_TIMEOUT = "PT3600S"
        try:
            p = protocol.Protocol(endpoint=self.hostname,
                                  transport='plaintext',
                                  username=self.username,
                                  password=self.password)

            shell_id = p.open_shell()

            command_id = p.run_command(shell_id, cmd)
            std_out, std_err, status_code = p.get_command_output(
                shell_id, command_id)

            p.cleanup_command(shell_id, command_id)
            p.close_shell(shell_id)

            return (std_out, std_err, status_code)

        except Exception as exc:
            LOG.exception(exc)
            raise exc

    def run_powershell_cmd(self, *args, **kvargs):
        list_args = " ".join(args)
        kv_args = " ".join(["-%s %s" % (k, v) for k, v in kvargs.iteritems()])
        full_cmd = "%s %s %s" % ('powershell', list_args, kv_args)
        s_out, s_err, r_code = self.run_wsman_cmd(full_cmd)
        if r_code != SUCCESS_RETURN_CODE:
            raise Exception("Command execution failed with code %(code)s:\n"
                            "Command: %(cmd)s\n"
                            "Output: %(output)s\n"
                            "Error: %(error)s" % {
                                'code': r_code,
                                'cmd': full_cmd,
                                'output': s_out,
                                'error': s_err})

        LOG.info('Command %(cmd)s result: %(output)s',
                 {'cmd': full_cmd, 'output': s_out})
        return s_out

    def get_powershell_cmd_attribute(self, *args, **kvargs):
        cmd = args[0]
        attribute = args[1]
        kv_args = " ".join(["-%s %s" % (k, v) for k, v in kvargs.iteritems()])
        full_cmd = "%s (%s %s).%s" % ('powershell', cmd, kv_args, attribute)
        s_out, s_err, r_code = self.run_wsman_cmd(full_cmd)
        if r_code != SUCCESS_RETURN_CODE:
            raise Exception("Command execution failed with code %(code)s:\n"
                            "Command: %(cmd)s\n"
                            "Output: %(output)s\n"
                            "Error: %(error)s" % {
                                'code': r_code,
                                'cmd': full_cmd,
                                'output': s_out,
                                'error': s_err})

        LOG.info('Command %(cmd)s result: %(output)s',
                 {'cmd': full_cmd, 'output': s_out})
        return s_out
