# Copyright 2014 Cloudbase Solutions Srl
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

import pdb
import os
from tempest import config
from tempest.openstack.common import log as logging
from tempest.common.utils.windows.remote_client import WinRemoteClient
from tempest.lis import manager
from tempest.scenario import utils as test_utils
from tempest import test

CONF = config.CONF

LOG = logging.getLogger(__name__)

load_tests = test_utils.load_tests_input_scenario_utils


class ISS(manager.LisBase):

    def setUp(self):
        super(ISS, self).setUp()
        # Setup image and flavor the test instance
        # Support both configured and injected values
        if not hasattr(self, 'image_ref'):
            self.image_ref = CONF.compute.image_ref
        if not hasattr(self, 'flavor_ref'):
            self.flavor_ref = CONF.compute.flavor_ref
        self.image_utils = test_utils.ImageUtils()
        if not self.image_utils.is_flavor_enough(self.flavor_ref,
                                                 self.image_ref):
            raise self.skipException(
                '{image} does not fit in {flavor}'.format(
                    image=self.image_ref, flavor=self.flavor_ref
                )
            )
        self.host_name = ""
        self.instance_name = ""
        self.run_ssh = CONF.compute.run_ssh and \
            self.image_utils.is_sshable_image(self.image_ref)
        self.ssh_user = self.image_utils.ssh_user(self.image_ref)
        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    def add_keypair(self):
        self.keypair = self.create_keypair()

    def boot_instance(self):
        # Create server with image and flavor from input scenario
        security_groups = [self.security_group]
        create_kwargs = {
            'key_name': self.keypair['name'],
            'security_groups': security_groups
        }
        self.instance = self.create_server(image=self.image_ref,
                                           flavor=self.flavor_ref,
                                           create_kwargs=create_kwargs)
        self.instance_name = self.instance["OS-EXT-SRV-ATTR:instance_name"]
        self.host_name = self.instance["OS-EXT-SRV-ATTR:hypervisor_hostname"]
        self._initiate_win_client(self.host_name)

    def nova_floating_ip_create(self):
        _, self.floating_ip = self.floating_ips_client.create_floating_ip()
        self.addCleanup(self.delete_wrapper,
                        self.floating_ips_client.delete_floating_ip,
                        self.floating_ip['id'])

    def nova_floating_ip_add(self):
        self.floating_ips_client.associate_floating_ip_to_server(
            self.floating_ip['ip'], self.instance['id'])

    def spawn_vm(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.boot_instance()
        self.nova_floating_ip_create()
        self.nova_floating_ip_add()
        self.server_id = self.instance['id']

    def _get_iss_status(self):
        """ Get the status of integrated shutdown services """

        s_out, s_err, e_code = self.win_client.get_powershell_cmd_attribute(
            'Get-VMIntegrationService', 'Enabled',
            ComputerName=self.host_name,
            VMName=self.instance_name,
            Name='Shutdown')
        LOG.info('Status of iss: %s', s_out)
        assert_msg = '%s\n%s\n%s' % ('Failed to get iss status.',
                                     str(s_out), str(s_err))
        self.assertTrue(e_code == 0, assert_msg)
        return s_out.lower().strip()

    def _disable_iss(self):
        """ Disable the integrated shutdown services """

        s_out, s_err, e_code = self.win_client.run_powershell_cmd(
            'Disable-VMIntegrationService',
            ComputerName=self.host_name,
            VMName=self.instance_name,
            Name='Shutdown')
        LOG.info('Disable iss result: %s', s_out)
        assert_msg = '%s\n%s\n%s' % ('Failed to disable iss.',
                                     str(s_out), str(s_err))
        self.assertTrue(e_code == 0, assert_msg)

    def _enable_iss(self):
        """ Enable the integrated shutdown services """

        s_out, s_err, e_code = self.win_client.run_powershell_cmd(
            'Enable-VMIntegrationService',
            ComputerName=self.host_name,
            VMName=self.instance_name,
            Name='Shutdown')
        LOG.info('Enable iss result: %s', s_out)
        assert_msg = '%s\n%s\n%s' % ('Failed to enable iss.',
                                     str(s_out), str(s_err))
        self.assertTrue(e_code == 0, assert_msg)

    def _verify_integrated_shutdown_services(self):
        status = self._get_iss_status()
        self.assertTrue('true'==status, "Integrated shutdown services disabled.")
        self._disable_iss()
        status = self._get_iss_status()
        self.assertTrue('false'==status, 'Failed to disable iss.')
        self._enable_iss()
        status = self._get_iss_status()
        self.assertTrue('true'==status, 'Failed to enable iss.')

    @test.attr(type=['smoke', 'core', 'iss'])
    @test.services('compute', 'network')
    def test_iss(self):
        self.spawn_vm()
        self.servers_client.stop(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'SHUTOFF')
        self.servers_client.start(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')
        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        try:
            self.linux_client.ping_host('127.0.0.1')

        except exceptions.SSHExecCommandFailed as exc:
            LOG.exception(exc)
            raise exc

    @test.attr(type=['core', 'iss'])
    @test.services('compute', 'network')
    def test_iss_reload(self):
        self.spawn_vm()
        self._verify_integrated_shutdown_services()
