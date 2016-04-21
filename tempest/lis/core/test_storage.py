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

from tempest.common import waiters
from tempest import config
from oslo_log import log as logging
from tempest.lis import manager
from tempest.scenario import utils as test_utils
from tempest import test

CONF = config.CONF

LOG = logging.getLogger(__name__)


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
        self.file_system = 'ext3'
        self.sector_size = 512
        self.disks = []
        self.disk_type = 'vhd'
        self.run_ssh = CONF.validation.run_validation and \
            self.image_utils.is_sshable_image(self.image_ref)
        self.ssh_user = CONF.validation.image_ssh_user

        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    def _test_storage(self, pos, vhd_type, exc_dsk_cnt, filesystem):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        if isinstance(pos, list):
            for position in pos:
                self.add_disk(self.instance_name, self.disk_type,
                              position, vhd_type, self.sector_size)
        else:
            self.add_disk(self.instance_name, self.disk_type,
                          pos, vhd_type, self.sector_size)
        self.start_vm(self.server_id)

        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.format_disk(exc_dsk_cnt, filesystem)
        self.servers_client.delete_server(self.instance['id'])

    def _test_large_disk(self, pos, vhd_type, exc_dsk_cnt, filesystem, size):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        if isinstance(pos, list):
            for position in pos:
                self.add_disk(self.instance_name, self.disk_type,
                              position, vhd_type, self.sector_size, size)
        else:
            self.add_disk(self.instance_name, self.disk_type,
                          pos, vhd_type, self.sector_size, size)
        self.start_vm(self.server_id)

        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.format_disk(exc_dsk_cnt, filesystem)
        self.servers_client.delete_server(self.instance['id'])

    def _test_add_passthrough(self, count, exc_dsk_cnt, filesystem):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        self.disks = []

        for dev in count:
            disk = self.add_passthrough_disk(dev)
            self.disks.append(disk)

        self.start_vm(self.server_id)
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        try:
            self.format_disk(exc_dsk_cnt, filesystem)

        except Exception as exc:
            LOG.exception(exc)
            self._log_console_output()
            raise exc
        finally:
            for disk in self.disks:
                self.detach_passthrough(disk)
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_add_passthrough(self, pos, exc_dsk_cnt, filesystem):
        self.spawn_vm()
        waiters.wait_for_server_status(self.servers_client, self.server_id, 'ACTIVE')
        if isinstance(pos, list):
            for position in pos:
                self.add_pass_disk(self.instance_name, position)
        else:
            self.add_pass_disk(self.instance_name, pos)
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.format_disk(exc_dsk_cnt, filesystem)
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_remove_passthrough(self, pos, vhd_type, exc_dsk_cnt):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        if isinstance(pos, list):
            for position in pos:
                self.add_pass_disk(self.instance_name, position)
        else:
            self.add_pass_disk(self.instance_name, pos)
        self.start_vm(self.server_id)

        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        for disk in self.disks:
            self.detach_disk(self.instance_name, disk)
        disk_count = self.count_disks()
        self.assertEqual(disk_count, 1)
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_add_storage(self, pos, vhd_type, exc_dsk_cnt, filesystem):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.boot_instance()
        self.nova_floating_ip_create()
        self.nova_floating_ip_add()
        server_id = self.instance['id']
        waiters.wait_for_server_status(self.servers_client, server_id, 'ACTIVE')

        if isinstance(pos, list):
            for position in pos:
                self.add_disk(self.instance_name, self.disk_type,
                              position, vhd_type, self.sector_size)
        else:
            self.add_disk(self.instance_name, self.disk_type,
                          pos, vhd_type, self.sector_size)

        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.format_disk(exc_dsk_cnt, filesystem)
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_remove(self, pos, vhd_type, exc_dsk_cnt):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        if isinstance(pos, list):
            for position in pos:
                self.add_disk(self.instance_name, self.disk_type,
                              position, vhd_type, self.sector_size)
        else:
            self.add_disk(self.instance_name, self.disk_type,
                          pos, vhd_type, self.sector_size)
        self.start_vm(self.server_id)

        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        for disk in self.disks:
            self.detach_disk(self.instance_name, disk)
        disk_count = self.count_disks()
        self.assertEqual(disk_count, 1)
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_swap(self, pos, vhd_type, exc_dsk_cnt, filesystem):
        self.spawn_vm()
        waiters.wait_for_server_status(self.servers_client, self.server_id, 'ACTIVE')

        if isinstance(pos, list):
            for position in pos:
                self.add_disk(self.instance_name, self.disk_type,
                              position, vhd_type, self.sector_size)
        else:
            self.add_disk(self.instance_name, self.disk_type,
                          pos, vhd_type, self.sector_size)

        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.format_disk(exc_dsk_cnt, filesystem)

        for disk in self.disks:
            self.detach_disk(self.instance_name, disk)
        disk_count = self.count_disks()
        self.assertEqual(disk_count, 1)
        self.servers_client.delete_server(self.instance['id'])

    def _test_hot_swap_smp(self, pos, vhd_type, exc_dsk_cnt, filesystem):
        self.spawn_vm()
        waiters.wait_for_server_status(self.servers_client, self.server_id, 'ACTIVE')
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        vcpu_count = self.linux_client.get_number_of_vcpus()
        if vcpu_count < 2:
            self.servers_client.stop_server(self.server_id)
            waiters.wait_for_server_status(self.servers_client,
                self.server_id, 'SHUTOFF')
            self.change_cpu(self.instance_name, 4)
            self.servers_client.start_server(self.server_id)
            waiters.wait_for_server_status(self.servers_client,
                self.server_id, 'ACTIVE')

        if isinstance(pos, list):
            for position in pos:
                self.add_disk(self.instance_name, self.disk_type,
                              position, vhd_type, self.sector_size)
        else:
            self.add_disk(self.instance_name, self.disk_type,
                          pos, vhd_type, self.sector_size)

        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.format_disk(exc_dsk_cnt, filesystem)

        for disk in self.disks:
            self.detach_disk(self.instance_name, disk)
        disk_count = self.count_disks()
        self.assertEqual(disk_count, 1)
        self.servers_client.delete_server(self.instance['id'])

    def _test_pass_ide(self, pos, exc_dsk_cnt, filesystem):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        if isinstance(pos, list):
            for position in pos:
                self.add_pass_disk(self.instance_name, position)
        else:
            self.add_pass_disk(self.instance_name, pos)
        self.start_vm(self.server_id)
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.format_disk(exc_dsk_cnt, filesystem)
        self.servers_client.delete_server(self.instance['id'])

    def _test_pass_offline(self, pos, exc_dsk_cnt, filesystem):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        if isinstance(pos, list):
            for position in pos:
                self.add_pass_disk(self.instance_name, position)
        else:
            self.add_pass_disk(self.instance_name, pos)
        self.start_vm(self.server_id)
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.format_disk(exc_dsk_cnt, filesystem)
        for disk in self.disks:
            self.make_passthrough_offline(disk)
        disk_count = self.count_disks()
        self.assertEqual(disk_count, 1)
        self.servers_client.delete_server(self.instance['id'])

    def _test_diff_disk(self, pos):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        self.add_diff_disk(self.instance_name, pos, self.disk_type)
        self.start_vm(self.server_id)
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        initial_disk_size = self.get_parent_disk_size(self.disks[0])
        self.increase_disk_size()
        final_disk_size = self.get_parent_disk_size(self.disks[0])
        self.assertEqual(initial_disk_size, final_disk_size)
        self.servers_client.delete_server(self.instance['id'])

    def _test_take_revert_snapshot(self):
        positions = [('SCSI', 1, 1), ('SCSI', 1, 2)]
        self.spawn_vm()
        vhd_type = 'Dynamic'
        self.stop_vm(self.server_id)
        self.add_disk(self.instance_name, 'vhd',
                      positions[0], vhd_type, self.sector_size)
        self.add_disk(self.instance_name, 'vhdx',
                      positions[1], vhd_type, self.sector_size)
        self.take_snapshot(self.instance_name, 'before_file')
        self.start_vm(self.server_id)

        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.linux_client.create_file('snapshot_test')
        self.stop_vm(self.server_id)
        self.take_snapshot(self.instance_name, 'after_file')

        self.revert_snapshot(self.instance_name, 'before_file')
        self.start_vm(self.server_id)
        result = self.linux_client.check_file_existence('snapshot_test')
        self.assertEqual(result, 0)
        self.servers_client.delete_server(self.instance['id'])

    def _test_fixed_ide(self):
        position = ('IDE', 1, 1)
        self._test_storage(position, 'Fixed', 1, self.file_system)

    def _test_pass_ide_0(self):
        position = ('IDE', 0, 1)
        self._test_pass_ide(position, 1, self.file_system)

    def _test_pass_ide_1(self):
        position = ('IDE', 1, 1)
        self._test_pass_ide(position, 1, self.file_system)

    def _test_pass_multiple_ide_0(self):
        positions = [('IDE', 0, 1), ('IDE', 1, 1)]
        self._test_pass_ide(positions, 2, self.file_system)

    def _test_pass_multiple_ide_1(self):
        positions = [('IDE', 0, 1), ('IDE', 1, 1)]
        self._test_pass_ide(positions, 2, self.file_system)

    def _test_stor_pass_offline(self):
        position = ('SCSI', 0, 1)
        self._test_pass_offline(position, 1, self.file_system)

    def _test_pass_scsi(self):
        position = ('SCSI', 0, 1)
        self._test_pass_ide(position, 1, self.file_system)

    def _test_multi_pass_scsi(self):
        positions = [('SCSI', 0, 1), ('SCSI', 1, 1)]
        self._test_pass_ide(positions, 2, self.file_system)

    def _test_pass_hot_add_multi_scsi(self):
        positions = [('SCSI', 0, 1), ('SCSI', 0, 2)]
        self._test_hot_add_passthrough(positions, 2, self.file_system)

    def _test_pass_hot_remove_multi_scsi(self):
        positions = [('SCSI', 0, 1), ('SCSI', 0, 2)]
        self._test_hot_remove_passthrough(positions, 2, self.file_system)

    def _test_fixed_scsi(self):
        position = ('SCSI', 1, 1)
        self._test_storage(position, 'Fixed', 1, self.file_system)

    def _test_dynamic_ide_1(self):
        position = ('IDE', 1, 1)
        self._test_storage(position, 'Dynamic', 1, self.file_system)

    def _test_dynamic_ide_0(self):
        position = ('IDE', 0, 1)
        self._test_storage(position, 'Dynamic', 1, self.file_system)

    def _test_dynamic_scsi(self):
        position = ('SCSI', 0, 1)
        self._test_storage(position, 'Dynamic', 1, self.file_system)

    def _test_multiple_ide_0(self):
        positions = [('IDE', 0, 1), ('IDE', 1, 1)]
        self._test_storage(positions, 'Dynamic', 2, self.file_system)

    def _test_multiple_ide_1(self):
        positions = [('IDE', 0, 1), ('IDE', 1, 1)]
        self._test_storage(positions, 'Dynamic', 2, self.file_system)

    def _test_multiple_scsi(self):
        positions = [('SCSI', 0, 0), ('SCSI', 0, 1)]
        self._test_storage(positions, 'Dynamic', 2, self.file_system)

    def _test_dynamic_hot_add_scsi(self):
        position = ('SCSI', 0, 1)
        self._test_hot_add_storage(position, 'Dynamic', 1, self.file_system)

    def _test_dynamic_hot_remove_scsi(self):
        position = ('SCSI', 0, 1)
        self._test_hot_remove(position, 'Dynamic', 1)

    def _test_dynamic_hot_swap_scsi(self):
        positions = [('SCSI', 0, 0), ('SCSI', 0, 1)]
        self._test_hot_swap(positions, 'Dynamic', 2, self.file_system)

    def _test_dynamic_hot_swap_smp_scsi(self):
        positions = [('SCSI', 0, 0), ('SCSI', 0, 1)]
        self._test_hot_swap_smp(positions, 'Dynamic', 2, self.file_system)

    def _test_dynamic_hot_add_multi_scsi(self):
        positions = [('SCSI', 0, 0), ('SCSI', 0, 1)]
        self._test_hot_add_storage(positions, 'Dynamic', 2, self.file_system)

    def _test_diff_disk_ide(self):
        position = ('IDE', 1, 1)
        self._test_diff_disk(position)

    def _test_diff_disk_scsi(self):
        position = ('SCSI', 1, 1)
        self._test_diff_disk(position)

    def _test_dynamic_large_scsi(self, size):
        position = ('SCSI', 1, 1)
        file_system = 'ext4'
        self._test_large_disk(position, 'Dynamic', 1, file_system, size)


class Storage(StorageBase):

    def setUp(self):
        super(Storage, self).setUp()

    @test.attr(type=['smoke', 'core_storage', 'snapshot', 'SCSI'])
    @test.services('compute', 'network')
    def test_take_revert_snapshot_scsi(self):
        self._test_take_revert_snapshot()

    @test.attr(type=['smoke', 'core_storage'])
    @test.services('compute', 'network')
    def test_iso(self):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        self.add_iso(self.instance_name)
        self.start_vm(self.server_id)
        waiters.wait_for_server_status(self.servers_client, self.server_id, 'ACTIVE')
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])

        self.check_iso()
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'core_storage'])
    @test.services('compute', 'network')
    def test_floppy(self):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        self.add_floppy_disk(self.instance_name)
        self.start_vm(self.server_id)
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_floppy()
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'core_storage'])
    @test.services('compute', 'network')
    def test_export_import(self):
        self.spawn_vm()
        waiters.wait_for_server_status(self.servers_client, self.server_id, 'ACTIVE')
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.export_import(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])


class TestVHD(StorageBase):

    def setUp(self):
        super(TestVHD, self).setUp()
        self.disk_type = 'vhd'
        self.sector_size = 512

    @test.attr(type=['smoke', 'core_storage', 'passthrough', 'IDE'])
    @test.services('compute', 'network')
    def test_passthrough_ide_0(self):
        self._test_pass_ide_0()

    @test.attr(type=['smoke', 'core_storage', 'passthrough', 'IDE'])
    @test.services('compute', 'network')
    def test_passthrough_ide_1(self):
        self._test_pass_ide_1()

    @test.attr(type=['core_storage', 'passthrough', 'IDE'])
    @test.services('compute', 'network')
    def test_passthrough_multi_ide_0(self):
        self._test_pass_multiple_ide_0()

    @test.attr(type=['core_storage', 'passthrough', 'IDE'])
    @test.services('compute', 'network')
    def test_passthrough_multi_ide_1(self):
        self._test_pass_multiple_ide_1()

    @test.attr(type=['core_storage', 'passthrough'])
    @test.services('compute', 'network')
    def test_passthrough_offline(self):
        self._test_stor_pass_offline()

    @test.attr(type=['smoke', 'core_storage', 'passthrough', 'SCSI'])
    @test.services('compute', 'network')
    def test_passthrough_scsi(self):
        self._test_pass_scsi()

    @test.attr(type=['core_storage', 'passthrough', 'SCSI'])
    @test.services('compute', 'network')
    def test_passthrough_multi_scsi(self):
        self._test_multi_pass_scsi()

    @test.attr(type=['core_storage', 'passthrough', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_passthrough_hot_add_scsi(self):
        self._test_pass_hot_add_multi_scsi()

    @test.attr(type=['smoke', 'core_storage', 'passthrough', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_passthrough_hot_remove_scsi(self):
        self._test_pass_hot_remove_multi_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'fixed', 'IDE'])
    @test.services('compute', 'network')
    def test_vhd_fixed_ide(self):
        self._test_fixed_ide()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'fixed', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhd_fixed_scsi(self):
        self._test_fixed_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_vhd_dynamic_ide_1(self):
        self._test_dynamic_ide_1()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_vhd_dynamic_ide_0(self):
        self._test_dynamic_ide_0()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhd_dynamic_scsi(self):
        self._test_dynamic_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_multiple_vhd_ide_0(self):
        self._test_multiple_ide_0()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_multiple_vhd_ide_1(self):
        self._test_multiple_ide_1()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_multiple_vhd_scsi(self):
        self._test_multiple_scsi()

    @test.attr(type=['core_storage', 'vhd', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhd_dynamic_btrfs_scsi(self):
        self.file_system = 'btrfs'
        self._test_dynamic_scsi()

    @test.attr(type=['core_storage', 'vhd', 'dynamic', 'large'])
    @test.services('compute', 'network')
    def test_dynamic_large_scsi(self):
        size = '20GB'
        self._test_dynamic_large_scsi(size)

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhd_dynamic_hot_add_scsi(self):
        self._test_dynamic_hot_add_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhd_dynamic_hot_remove_scsi(self):
        self._test_dynamic_hot_remove_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhd_dynamic_hot_add_multi_scsi(self):
        self._test_dynamic_hot_add_multi_scsi()

    @test.attr(type=['core_storage', 'vhd', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhd_dynamic_hot_swap_multi_scsi(self):
        self._test_dynamic_hot_swap_scsi()

    @test.attr(type=['core_storage', 'vhd', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhd_dynamic_hot_swap_smp_multi_scsi(self):
        self._test_dynamic_hot_swap_smp_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'differencing', 'IDE'])
    @test.services('compute', 'network')
    def test_vhd_differencing_ide(self):
        self._test_diff_disk_ide()

    @test.attr(type=['smoke', 'core_storage', 'vhd', 'differencing', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhd_differencing_scsi(self):
        self._test_diff_disk_scsi()


class TestVHDx(StorageBase):

    def setUp(self):
        super(TestVHDx, self).setUp()
        self.disk_type = 'vhdx'
        self.sector_size = 512

    @test.attr(type=['core_storage', 'vhdx', 'fixed', 'IDE'])
    @test.services('compute', 'network')
    def test_vhdx_fixed_ide(self):
        self._test_fixed_ide()

    @test.attr(type=['core_storage', 'vhdx', 'fixed', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_fixed_scsi(self):
        self._test_fixed_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_ide_1(self):
        self._test_dynamic_ide_1()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_ide_0(self):
        self._test_dynamic_ide_0()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_scsi(self):
        self._test_dynamic_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_multiple_vhdx_ide_0(self):
        self._test_multiple_ide_0()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_multiple_vhdx_ide_1(self):
        self._test_multiple_ide_1()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_multiple_vhdx_scsi(self):
        self._test_multiple_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_hot_add_scsi(self):
        self._test_dynamic_hot_add_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_hot_remove_scsi(self):
        self._test_dynamic_hot_remove_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_hot_swap_multi_scsi(self):
        self._test_dynamic_hot_swap_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_hot_swap_smp_multi_scsi(self):
        self._test_dynamic_hot_swap_smp_scsi()

    @test.attr(type=['smoke', 'core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_hot_add_multi_scsi(self):
        self._test_dynamic_hot_add_multi_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'large'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_large_scsi(self):
        size = '20GB'
        self._test_dynamic_large_scsi(size)

    @test.attr(type=['core_storage', 'vhdx', 'differencing', 'IDE'])
    @test.services('compute', 'network')
    def test_vhdx_differencing_ide(self):
        self._test_diff_disk_ide()

    @test.attr(type=['core_storage', 'vhdx', 'differencing', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_differencing_scsi(self):
        self._test_diff_disk_scsi()


class TestVHDx4K(StorageBase):

    def setUp(self):
        super(TestVHDx4K, self).setUp()
        self.disk_type = 'vhdx'
        self.sector_size = 4096

    @test.attr(type=['core_storage', 'vhdx', 'fixed', 'IDE'])
    @test.services('compute', 'network')
    def test_vhdx_4k_fixed_ide(self):
        self._test_fixed_ide()

    @test.attr(type=['core_storage', 'vhdx', 'fixed', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_4k_fixed_scsi(self):
        self._test_fixed_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_vhdx_4k_dynamic_ide_1(self):
        self._test_dynamic_ide_1()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_vhdx_4k_dynamic_ide_0(self):
        self._test_dynamic_ide_0()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_4k_dynamic_scsi(self):
        self._test_dynamic_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_multiple_vhdx_4k_ide_0(self):
        self._test_multiple_ide_0()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_multiple_vhdx_4k_ide_1(self):
        self._test_multiple_ide_1()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_multiple_vhdx_4k_scsi(self):
        self._test_multiple_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_4k_dynamic_hot_add_scsi(self):
        self._test_dynamic_hot_add_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_4k_dynamic_hot_remove_scsi(self):
        self._test_dynamic_hot_remove_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_4k_dynamic_hot_swap_multi_scsi(self):
        self._test_dynamic_hot_swap_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_4k_dynamic_hot_swap_smp_multi_scsi(self):
        self._test_dynamic_hot_swap_smp_scsi()

    @test.attr(type=['core_storage', 'vhdx', 'dynamic', 'hot', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_4k_dynamic_hot_add_multi_scsi(self):
        self._test_dynamic_hot_add_multi_scsi()
