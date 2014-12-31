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

from tempest import config
from tempest.openstack.common import log as logging
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
        self.ssh_user = CONF.compute.ssh_user
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

    def _test_shutdown_multi_cpu(self, max_cpu):
        for _ in range(2, max_cpu):
            self.stop_vm(self.server_id)
            self.change_cpu(self.instance_name, _)
            self.start_vm(self.server_id)
            vcpu_count = self.linux_client.get_number_of_vcpus()
            self.assertTrue(
                vcpu_count == _, "Expected %s , actual %s" % (_, vcpu_count))

    @test.attr(type=['smoke', 'core', 'smp'])
    @test.services('compute', 'network')
    def test_shutdown_smp(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self._test_shutdown_multi_cpu(5)

    @test.attr(type=['core', 'smp'])
    @test.services('compute', 'network')
    def test_shutdown_multi_cpu(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self._test_shutdown_multi_cpu(5)
