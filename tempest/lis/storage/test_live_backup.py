# Copyright 2015 Cloudbase Solutions Srl
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
from tempest import exceptions
from tempest import test
from tempest.lis import manager
from tempest.openstack.common import log as logging
from tempest.scenario import utils as test_utils

CONF = config.CONF

LOG = logging.getLogger(__name__)


class VSS(manager.LisBase):

    def setUp(self):
        super(VSS, self).setUp()
        # Setup image and flavor the test instance
        # Support both configured and injected values
        if not hasattr(self, 'image_ref'):
            self.image_ref = CONF.compute.image_ref
        if not hasattr(self, 'flavor_ref'):
            self.flavor_ref = CONF.compute.flavor_ref
        self.image_utils = test_utils.ImageUtils()
        if not self.image_utils.is_flavor_enough(self.flavor_ref,
                                                 self.image_ref):
            skip_message = '%(image)s does not fit in %(flavor)s' % {
                'image': self.image_ref,
                'flavor': self.flavor_ref}
            raise self.skipException(skip_message)

        self.host_name = ""
        self.instance_name = ""
        self.filename = '~/testfile.txt'
        self.run_ssh = (CONF.compute.run_ssh and
                        self.image_utils.is_sshable_image(self.image_ref))
        self.ssh_user = CONF.compute.ssh_user
        LOG.debug('Starting test for image: %(image)s, flavor: %(flavor)s.'
                  'User: %(ssh_user)s ' % {'image': self.image_ref,
                                           'flavor': self.flavor_ref,
                                           'ssh_user': self.ssh_user})

    def add_keypair(self):
        self.keypair = self.create_keypair()

    def boot_child_instance(self, image_id, host):
        # Create server with image and flavor from input scenario
        security_groups = [self.security_group]
        create_kwargs = {
            'key_name': self.keypair['name'],
            'security_groups': security_groups,
            'availability_zone': 'nova:%s' % host

        }
        return self.create_server(image=image_id,
                                  flavor=self.flavor_ref,
                                  create_kwargs=create_kwargs)

    def boot_instance(self):
        # Create server with image and flavor from input scenario
        security_groups = [self.security_group]
        create_kwargs = {
            'key_name': self.keypair['name'],
            'security_groups': security_groups,

        }
        return self.create_server(image=self.image_ref,
                                  flavor=self.flavor_ref,
                                  create_kwargs=create_kwargs)

    def nova_floating_ip_create(self):
        _, self.floating_ip = self.floating_ips_client.create_floating_ip()
        self.addCleanup(self.delete_wrapper,
                        self.floating_ips_client.delete_floating_ip,
                        self.floating_ip['id'])

    def nova_floating_ip_add(self, instance_id):
        self.floating_ips_client.associate_floating_ip_to_server(
            self.floating_ip['ip'], instance_id)

    def spawn_vm(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.instance = self.boot_instance()
        self.instance_name = self.instance["OS-EXT-SRV-ATTR:instance_name"]
        self.host_name = self.instance["OS-EXT-SRV-ATTR:hypervisor_hostname"]
        self._initiate_host_client(self.host_name)
        self.nova_floating_ip_create()
        self.nova_floating_ip_add(self.instance['id'])
        self.server_id = self.instance['id']

    def check_vss_deamon(self):
        """ Check if hv_vss_deamon runs on the vm """
        output = self.linux_client.verify_vss_deamon()
        self.assertIsNotNone(output, 'VSS daemon not present.')

    def create_file(self):
        """ Create a file on the vm """
        output = self.linux_client.create_file(self.filename)
        self.assertIsNotNone(output, 'Failed to create file on VM')
        LOG.info('Created file %s' % output)

    def verify_file(self):
        """ Verify if the file exists on the vm """
        output = self.linux_client.verify_file(self.filename)
        self.assertIsNotNone(output, 'Failed to check file on VM')
        LOG.info('File is present on the VM.')

    def delete_file(self):
        """ Delete the file from the vm """
        LOG.info('Deleting file from the the VM.')
        self.linux_client.delete_file(self.filename)

    def backup_vm(self, instance_name):
        """Take a VSS live backup of the VM"""
        script_location = "%s%s" % (self.script_folder,
                                    'setupscripts\\vss_backup.ps1')
        self.host_client.run_powershell_cmd(
            script_location,
            hvServer=self.host_name,
            vmName=instance_name,
            targetDrive=self.target_drive)

    def backup_vm_fail(self, instance_name):
        """Take a VSS live backup of the VM"""
        script_location = "%s%s" % (self.script_folder,
                                    'setupscripts\\vss_backup_fail.ps1')
        self.host_client.run_powershell_cmd(
            script_location,
            hvServer=self.host_name,
            vmName=instance_name,
            targetDrive=self.target_drive)

    def restore_vm(self, instance_name):
        """Restore the VM"""
        script_location = "%s%s" % (self.script_folder,
                                    'setupscripts\\vss_restore.ps1')
        self.host_client.run_powershell_cmd(
            script_location,
            hvServer=self.host_name,
            vmName=instance_name,
            targetDrive=self.target_drive)

    def _add_disks(self, pos, vhd_type, exc_dsk_cnt, filesystem):
        self.stop_vm(self.server_id)
        if not isinstance(pos, list):
            pos = [pos]
        for position in pos:
            self.add_disk(self.instance_name, self.disk_type,
                          position, vhd_type, self.sector_size)
        self.start_vm(self.server_id)
        self.linux_client.validate_authentication()
        self.format_disk(exc_dsk_cnt, filesystem)

    def _test_passthrough(self, count, exc_dsk_cnt, filesystem):
        self.disks = []
        for dev in count:
            disk = self.add_passthrough_disk(dev)
            self.disks.append(disk)
        try:
            self.format_disk(exc_dsk_cnt, filesystem)
            drive = self.create_pass_drive(self.instance_name)
            self.target_drive = drive + ':'
            self.backup_vm(self.instance_name)
            self.restore_vm(self.instance_name)

        except Exception as exc:
            LOG.exception(exc)
            self._log_console_output()
            raise exc
        finally:
            for disk in self.disks:
                self.detach_passthrough(disk)

    def _test_pass_ide(self, pos, exc_dsk_cnt, filesystem):
        if not isinstance(pos, list):
            pos = [pos]
        for position in pos:
            self.add_pass_disk(self.instance_name, position)
        self.format_disk(exc_dsk_cnt, filesystem)

    def create_child_vm(self, server_id):
        temp_image = self.create_server_snapshot(server_id)
        self.instance = self.boot_child_instance(
            temp_image['id'], self.instance["OS-EXT-SRV-ATTR:host"])
        self.servers_client.delete_server(self.server_id)
        self.instance_name = self.instance["OS-EXT-SRV-ATTR:instance_name"]
        self.nova_floating_ip_add(self.instance['id'])
        self.server_id = self.instance['id']

    def _add_disk_fail(self, pos, vhd_type, exc_dsk_cnt, filesystem):
        self.stop_vm(self.server_id)
        if not isinstance(pos, list):
            pos = [pos]
        for position in pos:
            self.add_disk(self.instance_name, self.disk_type,
                          position, vhd_type, self.sector_size)
        self.start_vm(self.server_id)
        self.linux_client.validate_authentication()
        self.freeze_fs(exc_dsk_cnt, filesystem)

    @test.attr(type=['smoke', 'storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_check_vss_daemon(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_base(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm(self.instance_name)
        self.restore_vm(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_ext3(self):
        self.sector_size = 512
        self.disk_type = 'vhd'
        self.disks = []
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        pos = [('IDE', 0, 1), ('SCSI', 0, 1)]
        self._add_disks(pos, 'DYNAMIC', 2, 'ext3')
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm(self.instance_name)
        self.restore_vm(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_ext4(self):
        self.sector_size = 512
        self.disk_type = 'vhd'
        self.disks = []
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        pos = [('IDE', 0, 1), ('SCSI', 0, 1)]
        self._add_disks(pos, 'DYNAMIC', 2, 'ext4')
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm(self.instance_name)
        self.restore_vm(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_reiserfs(self):
        self.sector_size = 512
        self.disk_type = 'vhd'
        self.disks = []
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        pos = [('IDE', 0, 1), ('SCSI', 0, 1)]
        self._add_disks(pos, 'DYNAMIC', 2, 'reiserfs')
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm(self.instance_name)
        self.restore_vm(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_vhd_attached(self):
        self.sector_size = 512
        self.disk_type = 'vhd'
        self.disks = []
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        pos = [('IDE', 0, 1), ('SCSI', 0, 1)]
        self._add_disks(pos, 'DYNAMIC', 2, 'ext3')
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm(self.instance_name)
        self.restore_vm(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_vhdx_attached(self):
        self.sector_size = 512
        self.disk_type = 'vhdx'
        self.disks = []
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        pos = [('IDE', 0, 1), ('SCSI', 0, 1)]
        self._add_disks(pos, 'DYNAMIC', 2, 'ext3')
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm(self.instance_name)
        self.restore_vm(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_file(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        self.create_file()
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm(self.instance_name)
        self.delete_file()
        self.restore_vm(self.instance_name)
        self.verify_file()
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_stop_state(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        self.stop_vm(self.server_id)
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm(self.instance_name)
        self.restore_vm(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_pause_state(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        self.pause_vm(self.server_id)
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm(self.instance_name)
        self.restore_vm(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_passthrough_ext4(self):
        self.sector_size = 512
        self.disk_type = 'passthrough'
        self.disks = []
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        self._test_pass_ide(('SCSI', 0, 0), 1, 'ext3')
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_iscsi(self):
        self.sector_size = 512
        self.disk_type = 'passthrough'
        self.disks = []
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        self._test_passthrough(['c', 'b'], 2, 'ext3')
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_no_network(self):
        self.sector_size = 512
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        try:
            self.stop_network()
        except exceptions.TimeoutException:
            pass
        except Exception as exc:
            LOG.exception(exc)
            raise exc

        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm(self.instance_name)
        self.restore_vm(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_3chained(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        self.create_child_vm(self.server_id)
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.stop_vm(self.server_id)
        self.backup_vm(self.instance_name)
        self.restore_vm(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_fail(self):
        self.sector_size = 512
        self.disk_type = 'vhd'
        self.disks = []
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        pos = [('IDE', 0, 1)]
        self._add_disk_fail(pos, 'DYNAMIC', 1, 'ext3')
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm_fail(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'storage', 'live_backup'])
    @test.services('compute', 'network')
    def test_vss_backup_restore_stress(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['ip'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_vss_deamon()
        self.stress_disk()
        drive = self.create_pass_drive(self.instance_name)
        self.target_drive = drive + ':'
        self.backup_vm(self.instance_name)
        self.restore_vm(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])
