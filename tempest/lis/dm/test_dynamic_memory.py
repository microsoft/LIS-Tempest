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

from tempest import config
from oslo_log import log as logging
from tempest.lis import manager
from tempest.scenario import utils as test_utils
from tempest import test

CONF = config.CONF

LOG = logging.getLogger(__name__)


class DynamicMemory(manager.LisBase):

    def setUp(self):
        super(DynamicMemory, self).setUp()
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
        self.ssh_user = CONF.validation.image_ssh_user
        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    @test.attr(type=['smoke', 'core', 'dynamic', 'memory'])
    @test.services('compute', 'network')
    def test_dm_basic(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.stop_vm(self.server_id)
        self.set_dynamic_memory(self.instance_name, '1GB', '1GB', '4GB', 50)
        self.start_vm(self.server_id)
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.linux_client.verify_lis_module('balloon')
        self.linux_client.verify_memory_hotadd_support()
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'core', 'dynamic', 'memory'])
    @test.services('compute', 'network')
    def test_memory_hot_add(self):
        self.spawn_vm()
        self._initiate_linux_client(
            self.floating_ip['floatingip']['floating_ip_address'],
            self.ssh_user, self.keypair['private_key'])
        self.stop_vm(self.server_id)

        # We set the memory of the VM under test. The numbers can be defined in
        # bytes or even MB, GB or percentage with the corresponding suffix
        self.set_dynamic_memory(self.instance_name, '1GB', '1GB', '6GB', 50)
        self.start_vm(self.server_id)
        self._initiate_linux_client(
            self.floating_ip['floatingip']['floating_ip_address'],
            self.ssh_user, self.keypair['private_key'])

        # Check if the hv_balloon is loaded
        self.linux_client.verify_lis_module('balloon')

        # Check if memory hotadd rule is present in the VM under test
        self.linux_client.verify_memory_hotadd_support()

        # Check if our preferred memory stress tool is installed
        # In this case we use stress-ng
        self.linux_client.check_installed_software('stress-ng')

        # The parameters for the memory pressure tool are determined according
        # to the distribution, version and memory setting
        self.determine_memory_stress_parameters()

        # Create lists with the VMs memory status in each stage of the test
        # Use these lists to check and compare Memory Assigned and Demand
        instance_memory_total_progress, instance_memory_demand_progress, \
            guest_memory_total_progress, guest_memory_used_progress = ([
            ] for i in range(4))

        # Check memory status on the Hyper-V host and in the Linux guest
        # before applying memory pressure
        host_memory_total = self.get_host_memory('total')
        host_memory_free = self.get_host_memory('free')

        instance_memory_total = self.get_ram_status(
            self.instance_name, 'MemoryAssigned')
        instance_memory_demand = self.get_ram_status(
            self.instance_name, 'MemoryDemand')

        guest_memory_total = self.linux_client.memory_check()
        guest_memory_free = self.linux_client.memory_check('MemFree')
        guest_memory_used = guest_memory_total - guest_memory_free

        instance_memory_total_progress.append(instance_memory_total)
        instance_memory_demand_progress.append(instance_memory_demand)
        guest_memory_total_progress.append(guest_memory_total)
        guest_memory_used_progress.append(guest_memory_used)

        # Apply memory stress
        self.linux_client.memory_hotadd(
            self.threads, self.chunk_size, self.duration, self.timeout)
        time.sleep(100)

        # Check memory status on the Hyper-V host and in the Linux guest
        # after memory stress has been applied
        instance_memory_total = self.get_ram_status(
            self.instance_name, 'MemoryAssigned')
        instance_memory_demand = self.get_ram_status(
            self.instance_name, 'MemoryDemand')

        guest_memory_total = self.linux_client.memory_check()
        guest_memory_free = self.linux_client.memory_check('MemFree')
        guest_memory_used = guest_memory_total - guest_memory_free

        instance_memory_total_progress.append(instance_memory_total)
        instance_memory_demand_progress.append(instance_memory_demand)
        guest_memory_total_progress.append(guest_memory_total)
        guest_memory_used_progress.append(guest_memory_used)

        # Compare the memory stats from before and after applying pressure
        # Compare the memory reported by Hyper-V and the one reported in the VM
        # and check for any weird behavior, if Hyper-V reports the correct stats
        # and if there aren't any discrepancies between the two
        # Also check swap. If it is unusually high, there is something wrong
        # with hot add support and the test should fail

        guest_memory_swap_total = self.linux_client.memory_check('SwapTotal')
        guest_memory_swap_free = self.linux_client.memory_check('SwapFree')
        guest_memory_swap_used = guest_memory_swap_total - \
            guest_memory_swap_free

        self.assetTrue(guest_memory_swap_used < 524288,
                       "Unusally high memory allocated in Swap")

        instance_memory_assigned_difference = \
            instance_memory_total_progress[1] - \
            instance_memory_total_progress[0]

        instance_memory_demand_difference = \
            instance_memory_demand_progress[1] - \
            instance_memory_demand_progress[0]

        guest_memory_total_difference = guest_memory_total_progress[1] - \
            guest_memory_total_progress[0]

        guest_memory_used_difference = guest_memory_used_progress[1] - \
            guest_memory_used_progress[0]
