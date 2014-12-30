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


class StorageBase(manager.LisBase):

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
        super(StorageBase, self).setUp()
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
        self.file_system = 'ext3'
        self.sector_size = 512
        self.disks = []
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

    def _test_storage(self, pos, vhd_type, expected_disk_count, filesystem):
        self.spawn_vm()
        self.servers_client.stop(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'SHUTOFF')
        if isinstance(pos, list):
            for position in pos:
                self.add_disk(
                    self.instance_name, self.disk_type, position, vhd_type, self.sector_size)
        else:
            self.add_disk(
                self.instance_name, self.disk_type, pos, vhd_type, self.sector_size)
        self.servers_client.start(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')

        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        self.format_disk(expected_disk_count, filesystem)
        self.servers_client.delete_server(self.instance['id'])

    def _test_add_passthrough(self, count, expected_disk_count, filesystem):
        self.spawn_vm()
        self.servers_client.stop(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'SHUTOFF')
        self.disks = []

        for dev in count:
            disk = self.add_passthrough_disk(dev)
            self.disks.append(disk)

        self.servers_client.start(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')
        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        try:
            self.format_disk(expected_disk_count, filesystem)

        except Exception as exc:
            LOG.exception(exc)
            self._log_console_output()
            raise exc
        finally:
            for disk in self.disks:
                self.detach_passthrough(disk)
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_add_passthrough(self, count, expected_disk_count, filesystem):
        self.spawn_vm()
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')
        self.disks = []

        for dev in count:
            disk = self.add_passthrough_disk(dev)
            self.disks.append(disk)

        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        try:
            self.format_disk(expected_disk_count, filesystem)

        except Exception as exc:
            LOG.exception(exc)
            self._log_console_output()
            raise exc
        finally:
            for disk in self.disks:
                self.detach_passthrough(disk)
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_remove_passthrough(self, count, expected_disk_count, filesystem):
        self.spawn_vm()
        self.servers_client.stop(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'SHUTOFF')
        self.disks = []

        for dev in count:
            disk = self.add_passthrough_disk(dev)
            self.disks.append(disk)

        self.servers_client.start(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')

        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        try:
            for disk in self.disks:
                self.detach_passthrough(disk)

            disk_count = self.count_disks()
            self.assertEqual(disk_count, 1)
        except Exception as exc:
            LOG.exception(exc)
            for disk in self.disks:
                self.detach_passthrough(disk)
            raise exc
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_add_storage(self, pos, vhd_type, expected_disk_count, filesystem):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.boot_instance()
        self.nova_floating_ip_create()
        self.nova_floating_ip_add()
        server_id = self.instance['id']
        self.servers_client.wait_for_server_status(server_id, 'ACTIVE')

        if isinstance(pos, list):
            for position in pos:
                self.add_disk(
                    self.instance_name, self.disk_type, position, vhd_type, self.sector_size)
        else:
            self.add_disk(
                self.instance_name, self.disk_type, pos, vhd_type, self.sector_size)

        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        self.format_disk(expected_disk_count, filesystem)
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_remove_storage(self, pos, vhd_type, expected_disk_count, filesystem):
        self.spawn_vm()
        self.servers_client.stop(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'SHUTOFF')
        if isinstance(pos, list):
            for position in pos:
                self.add_disk(
                    self.instance_name, self.disk_type, position, vhd_type, self.sector_size)
        else:
            self.add_disk(
                self.instance_name, self.disk_type, pos, vhd_type, self.sector_size)
        self.servers_client.start(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')

        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        for disk in self.disks:
            self.detach_disk(self.instance_name, disk)
        disk_count = self.count_disks()
        self.assertEqual(disk_count, 1)
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_swap_storage(self, pos, vhd_type, expected_disk_count, filesystem):
        self.spawn_vm()
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')

        if isinstance(pos, list):
            for position in pos:
                self.add_disk(
                    self.instance_name, self.disk_type, position, vhd_type, self.sector_size)
        else:
            self.add_disk(
                self.instance_name, self.disk_type, pos, vhd_type, self.sector_size)

        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        self.format_disk(expected_disk_count, filesystem)

        for disk in self.disks:
            self.detach_disk(self.instance_name, disk)
        disk_count = self.count_disks()
        self.assertEqual(disk_count, 1)
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_swap_smp_storage(self, pos, vhd_type, expected_disk_count, filesystem):
        self.spawn_vm()
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')
        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        vcpu_count = self.linux_client.get_number_of_vcpus()
        if vcpu_count < 2:
            self.servers_client.stop(self.server_id)
            self.servers_client.wait_for_server_status(self.server_id, 'SHUTOFF')
            self.change_cpu(self.instance_name, 4)
            self.servers_client.start(self.server_id)
            self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')

        if isinstance(pos, list):
            for position in pos:
                self.add_disk(
                    self.instance_name, self.disk_type, position, vhd_type, self.sector_size)
        else:
            self.add_disk(
                self.instance_name, self.disk_type, pos, vhd_type, self.sector_size)

        self.format_disk(expected_disk_count, filesystem)

        for disk in self.disks:
            self.detach_disk(self.instance_name, disk)
        disk_count = self.count_disks()
        self.assertEqual(disk_count, 1)
        self.servers_client.delete_server(self.instance['id'])

    def _test_pass_ide(self, pos, expected_disk_count, filesystem):
        self.spawn_vm()
        self.servers_client.stop(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'SHUTOFF')
        if isinstance(pos, list):
            for position in pos:
                self.add_pass_disk(
                    self.instance_name, position)
        else:
            self.add_pass_disk(
                self.instance_name, pos)
        self.servers_client.start(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')

        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        self.format_disk(expected_disk_count, filesystem)
        self.servers_client.delete_server(self.instance['id'])

    def _test_pass_offline(self, pos, expected_disk_count, filesystem):
        self.spawn_vm()
        self.servers_client.stop(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'SHUTOFF')
        if isinstance(pos, list):
            for position in pos:
                self.add_pass_disk(
                    self.instance_name, position)
        else:
            self.add_pass_disk(
                self.instance_name, pos)
        self.servers_client.start(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')

        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        self.format_disk(expected_disk_count, filesystem)
        for disk in self.disks:
            self.make_passthrough_offline(disk)
        disk_count = self.count_disks()
        self.assertEqual(disk_count, 1)
        self.servers_client.delete_server(self.instance['id'])

    def _test_diff_disk(self, pos):
        self.spawn_vm()
        self.servers_client.stop(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'SHUTOFF')
        self.add_diff_disk(self.instance_name, pos, self.disk_type)
        self.servers_client.start(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')
        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        initial_disk_size = self.get_parent_disk_size(self.disks[0])
        self.increase_disk_size()
        final_disk_size = self.get_parent_disk_size(self.disks[0])
        self.assertEqual(initial_disk_size, final_disk_size)
        self.servers_client.delete_server(self.instance['id'])

    def _test_take_revert_snapshot(self):
        positions = [('SCSI', 1, 1), ('SCSI', 1, 2)]
        self.spawn_vm()
        vhd_type = 'Dynamic'
        self.servers_client.stop(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'SHUTOFF')
        self.add_disk(self.instance_name, 'vhd', positions[0], vhd_type, self.sector_size)
        self.add_disk(self.instance_name, 'vhdx', positions[1], vhd_type, self.sector_size)
        self.take_snapshot(self.instance_name, 'before_file')
        self.servers_client.start(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')

        self._initiate_linux_client(self.floating_ip['ip'], self.image_utils.ssh_user(
            self.image_ref), self.keypair['private_key'])
        self.linux_client.create_file('snapshot_test')
        self.servers_client.stop(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'SHUTOFF')
        self.take_snapshot(self.instance_name, 'after_file')

        self.revert_snapshot(self.instance_name, 'before_file')
        self.servers_client.start(self.server_id)
        self.servers_client.wait_for_server_status(self.server_id, 'ACTIVE')
        result = self.linux_client.check_file_existence('snapshot_test')
        self.assertEqual(result, 0)
        self.servers_client.delete_server(self.instance['id'])

    def _test_storage_fixed_ide(self):
        position = ('IDE', 1, 1)
        self._test_storage(position, 'Fixed', 1, self.file_system)

    def _test_storage_pass_ide_0(self):
        position = ('IDE', 0, 1)
        self._test_pass_ide(position, 1, self.file_system)

    def _test_storage_pass_ide_1(self):
        position = ('IDE', 1, 1)
        self._test_pass_ide(position, 1, self.file_system)

    def _test_storage_pass_multiple_ide_0(self):
        positions = [('IDE', 0, 1), ('IDE', 1, 1)]
        self._test_pass_ide(positions, 2, self.file_system)

    def _test_storage_pass_multiple_ide_1(self):
        positions = [('IDE', 0, 1), ('IDE', 1, 1)]
        self._test_pass_ide(positions, 2, self.file_system)

    def _test_storage_pass_offline(self):
        position = ('SCSI', 0, 1)
        self._test_pass_offline(position, 1, self.file_system)

    def _test_storage_pass_scsi(self):
        count = ['b']
        self._test_add_passthrough(count, 1, self.file_system)

    def _test_storage_multi_pass_scsi(self):
        count = ['b', 'c']
        self._test_add_passthrough(count, 2, self.file_system)

    def _test_storage_pass_hot_add_multi_scsi(self):
        count = ['b', 'c']
        self._test_hot_add_passthrough(count, 2, self.file_system)

    def _test_storage_pass_hot_remove_multi_scsi(self):
        count = ['b', 'c']
        self._test_hot_remove_passthrough(count, 2, self.file_system)

    def _test_storage_fixed_scsi(self):
        position = ('SCSI', 1, 1)
        self._test_storage(position, 'Fixed', 1, self.file_system)

    def _test_storage_dynamic_ide_1(self):
        position = ('IDE', 1, 1)
        self._test_storage(position, 'Dynamic', 1, self.file_system)

    def _test_storage_dynamic_ide_0(self):
        position = ('IDE', 0, 1)
        self._test_storage(position, 'Dynamic', 1, self.file_system)

    def _test_storage_dynamic_scsi(self):
        position = ('SCSI', 0, 1)
        self._test_storage(position, 'Dynamic', 1, self.file_system)

    def _test_storage_multiple_ide_0(self):
        positions = [('IDE', 0, 1), ('IDE', 1, 1)]
        self._test_storage(positions, 'Dynamic',  2, self.file_system)

    def _test_storage_multiple_ide_1(self):
        positions = [('IDE', 0, 1), ('IDE', 1, 1)]
        self._test_storage(positions, 'Dynamic', 2, self.file_system)

    def _test_storage_multiple_scsi(self):
        positions = [('SCSI', 0, 0), ('SCSI', 0, 1)]
        self._test_storage(positions, 'Dynamic', 2, self.file_system)

    def _test_storage_dynamic_hot_add_scsi(self):
        position = ('SCSI', 0, 1)
        self._test_hot_add_storage(position, 'Dynamic', 1, self.file_system)

    def _test_storage_dynamic_hot_remove_scsi(self):
        position = ('SCSI', 0, 1)
        self._test_hot_remove_storage(position, 'Dynamic', 1, self.file_system)

    def _test_storage_dynamic_hot_swap_scsi(self):
        positions = [('SCSI', 0, 0), ('SCSI', 0, 1)]
        self._test_hot_swap_storage(positions, 'Dynamic', 2, self.file_system)

    def _test_storage_dynamic_hot_swap_smp_scsi(self):
        positions = [('SCSI', 0, 0), ('SCSI', 0, 1)]
        self._test_hot_swap_smp_storage(positions, 'Dynamic', 2, self.file_system)

    def _test_storage_dynamic_hot_add_multi_scsi(self):
        positions = [('SCSI', 0, 0), ('SCSI', 0, 1)]
        self._test_hot_add_storage(positions, 'Dynamic', 2, self.file_system)

    def _test_diff_disk_ide(self):
        position = ('IDE', 1, 1)
        self._test_diff_disk(position)

    def _test_diff_disk_scsi(self):
        position = ('SCSI', 1, 1)
        self._test_diff_disk(position)


class Storage(StorageBase):

    def setUp(self):
        super(Storage, self).setUp()

    @test.attr(type=['smoke', 'core_storage', 'snapshot', 'SCSI'])
    @test.services('compute', 'network')
    def test_take_revert_snapshot_scsi(self):
        self._test_take_revert_snapshot()


class TestVHD(StorageBase):

    def setUp(self):
        super(TestVHD, self).setUp()
        self.disk_type = 'vhd'
        self.sector_size = 512

    @test.attr(type=['smoke', 'core_storage', 'passthrough', 'IDE'])
    @test.services('compute', 'network')
    def test_passthrough_ide_0(self):
        self._test_storage_pass_ide_0()

    @test.attr(type=['smoke', 'core_storage', 'passthrough', 'IDE'])
    @test.services('compute', 'network')
    def test_passthrough_ide_1(self):
        self._test_storage_pass_ide_1()

    @test.attr(type=[ 'core_storage', 'passthrough', 'IDE'])
    @test.services('compute', 'network')
    def test_passthrough_multi_ide_0(self):
        self._test_storage_pass_multiple_ide_0()

    @test.attr(type=['core_storage', 'passthrough', 'IDE'])
    @test.services('compute', 'network')
    def test_passthrough_multi_ide_1(self):
        self._test_storage_pass_multiple_ide_1()

    @test.attr(type=['core_storage', 'passthrough'])
    @test.services('compute', 'network')
    def test_passthrough_offline(self):
        self._test_storage_pass_offline()

    @test.attr(type=['smoke', 'core_storage', 'passthrough', 'SCSI'])
    @test.services('compute', 'network')
    def test_passthrough_scsi(self):
        self._test_storage_pass_scsi()

    @test.attr(type=[ 'core_storage', 'passthrough', 'SCSI'])
    @test.services('compute', 'network')
    def test_passthrough_multi_scsi(self):
        self._test_storage_multi_pass_scsi()

    @test.attr(type=['core_storage', 'passthrough', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_passthrough_hot_add_scsi(self):
        self._test_storage_pass_hot_add_multi_scsi()

    @test.attr(type=['smoke', 'core_storage', 'passthrough', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_passthrough_hot_remove_scsi(self):
        self._test_storage_pass_hot_remove_multi_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'fixed', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_vhd_fixed_ide(self):
        self._test_storage_fixed_ide()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'fixed', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhd_fixed_scsi(self):
        self._test_storage_fixed_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_vhd_dynamic_ide_1(self):
        self._test_storage_dynamic_ide_1()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_vhd_dynamic_ide_0(self):
        self._test_storage_dynamic_ide_0()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhd_dynamic_scsi(self):
        self._test_storage_dynamic_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_multiple_vhd_ide_0(self):
        self._test_storage_multiple_ide_0()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_multiple_vhd_ide_1(self):
        self._test_storage_multiple_ide_1()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_multiple_vhd_scsi(self):
        self._test_storage_multiple_scsi()

    @test.attr(type=['core_storage', 'vhd', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhd_dynamic_btrfs_scsi(self):
        self.file_system = 'btrfs'
        self._test_storage_dynamic_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhd_dynamic_hot_add_scsi(self):
        self._test_storage_dynamic_hot_add_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhd_dynamic_hot_remove_scsi(self):
        self._test_storage_dynamic_hot_remove_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhd_dynamic_hot_add_multi_scsi(self):
        self._test_storage_dynamic_hot_add_multi_scsi()

    @test.attr(type=['core_storage', 'vhd', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhd_dynamic_hot_swap_multi_scsi(self):
        self._test_storage_dynamic_hot_swap_scsi()

    @test.attr(type=['core_storage', 'vhd', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhd_dynamic_hot_swap_smp_multi_scsi(self):
        self._test_storage_dynamic_hot_swap_smp_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'differencing', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_vhd_differencing_ide(self):
        self._test_diff_disk_ide()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'differencing', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhd_differencing_scsi(self):
        self._test_diff_disk_scsi()


class TestVHDx(StorageBase):

    def setUp(self):
        super(TestVHDx, self).setUp()
        self.disk_type = 'vhdx'
        self.sector_size = 512

    @test.attr(type=['core_storage', 'vhdx', 'fixed', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_vhdx_fixed_ide(self):
        self._test_storage_fixed_ide()

    @test.attr(type=['core_storage', 'vhdx', 'fixed', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_fixed_scsi(self):
        self._test_storage_fixed_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_vhdx_dynamic_ide_1(self):
        self._test_storage_dynamic_ide_1()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_vhdx_dynamic_ide_0(self):
        self._test_storage_dynamic_ide_0()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_dynamic_scsi(self):
        self._test_storage_dynamic_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_multiple_vhdx_ide_0(self):
        self._test_storage_multiple_ide_0()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_multiple_vhdx_ide_1(self):
        self._test_storage_multiple_ide_1()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_multiple_vhdx_scsi(self):
        self._test_storage_multiple_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_dynamic_hot_add_scsi(self):
        self._test_storage_dynamic_hot_add_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_dynamic_hot_remove_scsi(self):
        self._test_storage_dynamic_hot_remove_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_dynamic_hot_swap_multi_scsi(self):
        self._test_storage_dynamic_hot_swap_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_dynamic_hot_swap_smp_multi_scsi(self):
        self._test_storage_dynamic_hot_swap_smp_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_dynamic_hot_add_multi_scsi(self):
        self._test_storage_dynamic_hot_add_multi_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'differencing', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_vhdx_differencing_ide(self):
        self._test_diff_disk_ide()

    @test.attr(type=['core_storage', 'vhdx', 'differencing', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_differencing_scsi(self):
        self._test_diff_disk_scsi()


class TestVHDx4K(StorageBase):

    def setUp(self):
        super(TestVHDx4K, self).setUp()
        self.disk_type = 'vhdx'
        self.sector_size = 4096

    @test.attr(type=['core_storage', 'vhdx', 'fixed', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_vhdx_4k_fixed_ide(self):
        self._test_storage_fixed_ide()

    @test.attr(type=['core_storage', 'vhdx', 'fixed', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_4k_fixed_scsi(self):
        self._test_storage_fixed_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_vhdx_4k_dynamic_ide_1(self):
        self._test_storage_dynamic_ide_1()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_vhdx_4k_dynamic_ide_0(self):
        self._test_storage_dynamic_ide_0()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_4k_dynamic_scsi(self):
        self._test_storage_dynamic_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_multiple_vhdx_4k_ide_0(self):
        self._test_storage_multiple_ide_0()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_storage_multiple_vhdx_4k_ide_1(self):
        self._test_storage_multiple_ide_1()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_multiple_vhdx_4k_scsi(self):
        self._test_storage_multiple_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_4k_dynamic_hot_add_scsi(self):
        self._test_storage_dynamic_hot_add_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_4k_dynamic_hot_remove_scsi(self):
        self._test_storage_dynamic_hot_remove_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_4k_dynamic_hot_swap_multi_scsi(self):
        self._test_storage_dynamic_hot_swap_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_4k_dynamic_hot_swap_smp_multi_scsi(self):
        self._test_storage_dynamic_hot_swap_smp_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_storage_vhdx_4k_dynamic_hot_add_multi_scsi(self):
        self._test_storage_dynamic_hot_add_multi_scsi()

