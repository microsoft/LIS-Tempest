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
import netaddr
import os
from tempest import config
from tempest.common.utils import data_utils
from tempest.common.utils.windows.remote_client import WinRemoteClient
from tempest.lis import manager
from oslo_log import log as logging
from tempest.scenario import utils as test_utils
from tempest import test
import pdb

CONF = config.CONF

LOG = logging.getLogger(__name__)

load_tests = test_utils.load_tests_input_scenario_utils


class Network(manager.LisBase):

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
        super(Network, self).setUp()
        # Setup image and flavor the test instance
        # Support both configured and injected values
        if not hasattr(self, 'image_ref'):
            self.image_ref = CONF.compute.image_ref
        if not hasattr(self, 'flavor_ref'):
            self.flavor_ref = CONF.compute.flavor_ref
        self.image_utils = test_utils.ImageUtils(self.manager)
        if not self.image_utils.is_flavor_enough(self.flavor_ref,
                                                 self.image_ref):
            raise self.skipException(
                '{image} does not fit in {flavor}'.format(
                    image=self.image_ref, flavor=self.flavor_ref
                )
            )
        self.host_name = ""
        self.instance_name = ""
        self.run_ssh = CONF.validation.run_validation and \
            self.image_utils.is_sshable_image(self.image_ref)
        self.ssh_user = self.image_utils.ssh_user(self.image_ref)
        self.host_username = CONF.host_credentials.host_user_name
        self.host_password = CONF.host_credentials.host_password
        self.scriptfolder = CONF.host_credentials.host_setupscripts_folder
        self.lis_private_network = CONF.lis.private_network

        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    def _initiate_wsman(self, host_name):
        try:
            self.wsmancmd = WinRemoteClient(
                host_name, self.host_username, self.host_password)

        except Exception as exc:
            LOG.exception(exc)
            raise exc

    def verify_ssh(self):
        if self.run_ssh:
            # Obtain a floating IP
            floating_network_id = CONF.network.public_network_id
            self.floating_ip = self.floating_ips_client.create_floatingip(floating_network_id=floating_network_id)
            self.addCleanup(self.delete_wrapper,
                    self.floating_ips_client.delete_floatingip,
                    self.floating_ip['floatingip']['floating_ip_address'])
            # Attach a floating IP
            self.compute_floating_ips_client.associate_floating_ip_to_server(
                self.floating_ip['floatingip']['floating_ip_address'], self.instance['id'])
            # Check ssh
            try:
                self.get_remote_client(
                    ip_address=self.floating_ip['floatingip']['floating_ip_address'],
                    username=self.image_utils.ssh_user(self.image_ref),
                    private_key=self.keypair['private_key'])
            except Exception:
                LOG.exception('ssh to server failed')
                self._log_console_output()
                raise

    def verify_external_ping(self, destination_ip):
        if self.run_ssh:
            # Obtain a floating IP
            floating_network_id = CONF.network.public_network_id
            self.floating_ip = self.floating_ips_client.create_floatingip(floating_network_id=floating_network_id)
            self.addCleanup(self.delete_wrapper,
                    self.floating_ips_client.delete_floatingip,
                    self.floating_ip['floatingip']['floating_ip_address'])
            # Attach a floating IP
            self.compute_floating_ips_client.associate_floating_ip_to_server(
                self.floating_ip['floatingip']['floating_ip_address'], self.instance['id'])
            # Check lis presence
            try:
                linux_client = self.get_remote_client(
                    ip_address=self.floating_ip['floatingip']['floating_ip_address'],
                    username=self.image_utils.ssh_user(self.image_ref),
                    private_key=self.keypair['private_key'])

                output = linux_client.verify_ping(destination_ip)
                LOG.info('Ping resuls ${0}'.format(output))
                self.assertNotEqual(0, output)
            except Exception:
                LOG.exception('ssh to server failed')
                self._log_console_output()
                raise


class Basic(Network):

    def setUp(self):
        super(Basic, self).setUp()

    @test.services('compute', 'network')
    def test_configure_network(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.boot_instance()
        self.verify_ssh()
        self.servers_client.delete_server(self.instance['id'])

    @test.services('compute', 'network')
    def test_external_network(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.boot_instance()
        self.verify_external_ping('8.8.8.8')
        self.servers_client.delete_server(self.instance['id'])