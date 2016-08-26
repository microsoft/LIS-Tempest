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


class StorageResize(manager.LisBase):

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
        super(StorageResize, self).setUp()
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
        self.file_system = 'ext4'
        self.sector_size = 512
        self.disks = []
        self.disk_type = 'vhdx'
        self.run_ssh = CONF.validation.run_validation and \
            self.image_utils.is_sshable_image(self.image_ref)
        self.ssh_user = CONF.validation.image_ssh_user

        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    def _create_vm_with_disk(self, pos, vhd_type, size, exc_dsk_cnt, filesys):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        self.add_disk(self.instance_name, self.disk_type,
                      pos, vhd_type, self.sector_size, size)
        self.start_vm(self.server_id)

        self._initiate_linux_client(
            self.floating_ip['floatingip']['floating_ip_address'],
            self.ssh_user,
            self.keypair['private_key'])
        self.format_disk(exc_dsk_cnt, filesys)
        self.linux_client.delete_partition("sdb")

    def _test_resize(
            self, pos, vhd_type, exc_dsk_cnt, filesystem, size, action):
        if not self.disks:
            self._create_vm_with_disk(
                pos, vhd_type, size, exc_dsk_cnt, filesystem)

        if pos[0] == 'IDE':
            self.stop_vm(self.server_id)

        for disk in self.disks:
            new_size = self.resize_disk(self.instance_name, disk, size, action)

        if pos[0] == 'IDE':
            self.start_vm(self.server_id)
            self._initiate_linux_client(
                self.floating_ip['floatingip']['floating_ip_address'],
                self.ssh_user,
                self.keypair['private_key'])

        self.linux_client.disk_rescan(60)
        size_check = self.linux_client.get_disks_size("sdb", 10)
        self.assertTrue(new_size == size_check,
                        "ERROR: New disk size not detected.")

        if action == 'growfs' and filesystem == 'xfs':
            self.linux_client.recreate_partition("sdb")
            self.linux_client.mount("sdb1")
            self.linux_client.grow_xfs("/mnt")
            result = self.linux_client.check_file_existence(
                '/mnt/Example/data')
            self.assertEqual(result, 0)
        else:
            self.format_disk(exc_dsk_cnt, filesystem)
            self.linux_client.delete_partition("sdb")

    def _test_fixed_ide(self, action):
        position = ('IDE', 0, 1)
        self._test_resize(position, 'Fixed', 1,
                          self.file_system, self.size, action)

    def _test_dynamic_ide(self, action):
        position = ('IDE', 0, 1)
        self._test_resize(position, 'Dynamic', 1,
                          self.file_system, self.size, action)

    def _test_dynamic_scsi(self, action):
        position = ('SCSI', 0, 1)
        self._test_resize(position, 'Dynamic', 1,
                          self.file_system, self.size, action)


class TestVHDxResize(StorageResize):

    def setUp(self):
        super(TestVHDxResize, self).setUp()
        self.disk_type = 'vhdx'
        self.sector_size = 512
        self.size = '3GB'

    @test.attr(type=['resize', 'vhdx', 'fixed', 'SCSI', 'IDE'])
    @test.services('compute', 'network')
    def test_vhdx_fixed_ide_grow(self):
        action = 'grow'
        self._test_fixed_ide(action)

    @test.attr(type=['smoke', 'resize', 'vhdx', 'dynamic', 'IDE'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_ide_grow(self):
        action = 'grow'
        self._test_dynamic_ide(action)

    @test.attr(type=['smoke', 'resize', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_scsi_grow(self):
        action = 'grow'
        self._test_dynamic_scsi(action)

    @test.attr(type=['resize', 'vhdx', 'dynamic', 'large', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_large_scsi_grow(self):
        action = 'grow'
        self.size = '20GB'
        self._test_dynamic_scsi(action)

    @test.attr(type=['smoke', 'resize', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_scsi_shrink(self):
        action = 'shrink'
        self._test_dynamic_scsi(action)

    @test.attr(type=['smoke', 'resize', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_dynamic_scsi_grow_shrink(self):
        action = 'grow'
        self._test_dynamic_scsi(action)
        action = 'shrink'
        self._test_dynamic_scsi(action)

    @test.attr(type=['smoke', 'resize', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_resize_dynamic_scsi_growfs(self):
        action = 'growfs'
        self.file_system = 'xfs'
        self._test_dynamic_scsi(action)


class TestVHDx4KResize(StorageResize):

    def setUp(self):
        super(TestVHDx4KResize, self).setUp()
        self.disk_type = 'vhdx'
        self.sector_size = 4096
        self.size = '3GB'

    @test.attr(type=['resize', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_resize_4k_dynamic_scsi_grow(self):
        action = 'grow'
        self._test_dynamic_scsi(action)

    @test.attr(type=['resize', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_resize_4k_dynamic_scsi_shrink(self):
        action = 'shrink'
        self._test_dynamic_scsi(action)

    @test.attr(type=['smoke', 'resize', 'vhdx', 'dynamic', 'SCSI'])
    @test.services('compute', 'network')
    def test_vhdx_resize_4k_dynamic_scsi_growfs(self):
        action = 'growfs'
        self.file_system = 'xfs'
        self._test_dynamic_scsi(action)
