# Copyright 2014 Cloudbase Solutions
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

from tempest import config
from tempest.common.utils.windows.remote_client import WinRemoteClient
from tempest.lis import manager
from tempest.openstack.common import log as logging
from tempest.scenario import utils as test_utils
from tempest import test

CONF = config.CONF

LOG = logging.getLogger(__name__)

load_tests = test_utils.load_tests_input_scenario_utils


class TestLis(manager.ScenarioTest):

    """
    This smoke test case follows this basic set of operations:

     * Create a keypair for use in launching an instance
     * Create a security group to control network access in instance
     * Add simple permissive rules to the security group
     * Launch an instance
     * Pause/unpause the instance
     * Suspend/resume the instance
     * Terminate the instance
    """

    def setUp(self):
        super(TestLis, self).setUp()
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

    def verify_heartbeat(self):
        """ use actual credentials from conf file"""
        username = CONF.host_credentials.host_user_name
        password = CONF.host_credentials.host_password
        cmd = 'powershell -Command $(Get-VMIntegrationService -ComputerName ' + self.host_name +' -VMName '+  self.instance_name +' -Name Heartbeat).Enabled'

        wsmancmd = WinRemoteClient(self.host_name, username, password)
        LOG.debug('Sending command %s', cmd)
        try:
            std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd)

        except Exception as exc:
            LOG.exception(exc)
            raise exc

        LOG.debug('Command std_out: %s', std_out)
        LOG.debug('Command std_err: %s', std_err)

        ok = "True" in std_out
        self.assertEqual(ok, True)

    @test.services('compute', 'network')
    def test_server_lis_heartbeat(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.boot_instance()
        self.verify_heartbeat()
        self.servers_client.delete_server(self.instance['id'])
