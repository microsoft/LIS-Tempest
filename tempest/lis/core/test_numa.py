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

import time

from oslo_log import log as logging
from tempest import config, exceptions, test
from tempest.lib import exceptions as lib_exc
from tempest.lis import manager
from tempest.scenario import utils as test_utils

CONF = config.CONF

LOG = logging.getLogger(__name__)


class Numa(manager.LisBase):

    def setUp(self):
        super(Numa, self).setUp()
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
        self.linux_client = ""
        self.run_ssh = CONF.validation.run_validation and \
            self.image_utils.is_sshable_image(self.image_ref)
        self.ssh_user = CONF.validation.image_ssh_user
        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    def check_numa_nodes(self, cpus, numa_nodes, sockets):
        self.stop_vm(self.server_id)
        self.disable_dynamic_memory(self.instance_name)
        self.change_cpu(self.instance_name, cpus)
        self.change_cpu_numa(self.instance_name, numa_nodes, sockets)
        self.start_vm(self.server_id)

        host_numa_nodes = self.host_client.get_powershell_cmd_attribute(
            'Get-VM', 'NumaNodesCount',
            ComputerName=self.host_name,
            VMName=self.instance_name)
        try:
            self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                        self.ssh_user, self.keypair['private_key'])

            kernel_version = self.linux_client.exec_command('uname -r')
            self.assertFalse(kernel_version.startswith("2.6") or kernel_version.endswith(".i686"),
                             "NUMA not supported for kernel:%s" % (kernel_version))

            vcpu_count = self.linux_client.get_number_of_vcpus()
            if cpus == 8:
                vcpu_count = vcpu_count / 4

            self.assertTrue(int(host_numa_nodes) == int(vcpu_count),
                            "Numa nodes and number of CPU does not match. Expected %s , actual %s" % (vcpu_count, host_numa_nodes))

            guest_nodes = self.linux_client.exec_command('sudo numactl -H | grep cpu | wc -l')
            self.assertTrue(int(host_numa_nodes) == int(guest_nodes),
                            "Error: Guest VM presented value %s and the host has %s" % (host_numa_nodes, guest_nodes))

            time.sleep(120)

            LOG.info('Numa nodes are matching. Expected {0} , actual {1}'.format(host_numa_nodes, guest_nodes))
        except Exception:
            LOG.exception('ssh to server failed')
            self._log_console_output()
            raise

    @test.attr(type=['core', 'numa'])
    @test.services('compute', 'network')
    def test_numa_nodes(self):
        """This function compares the host provided Numa Nodes values
           with the numbers of CPUs and ones detected on a Linux guest VM."""

        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_numa_nodes(4, 1, 1)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['core', 'numa'])
    @test.services('compute', 'network')
    def test_numa_maximum(self):
        """This function compares the host provided Numa Nodes values
           with the numbers of CPUs and ones detected on a Linux guest VM."""

        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_numa_nodes(8, 4, 2)
        self.servers_client.delete_server(self.instance['id'])
