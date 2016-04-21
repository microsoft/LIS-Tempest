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
from oslo_log import log as logging
from tempest.common.utils.windows.remote_client import WinRemoteClient
from tempest.lis import manager
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
        self.filename = '~/testfile.txt'
        self.deamon = 'hv_vss_daemon'
        self.username = CONF.host_credentials.host_user_name
        self.passwd = CONF.host_credentials.host_password
        self.scriptfolder = CONF.host_credentials.host_setupscripts_folder
        self.targetdrive = CONF.host_credentials.host_vssbackup_drive
        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    def check_vss_deamon(self):
        """ Check if hv_vss_deamon runs on the vm """
        try:
            linux_client = self.get_remote_client(
                ip_address=self.floating_ip['floatingip']['floating_ip_address'],
                username=self.image_utils.ssh_user(self.image_ref),
                private_key=self.keypair['private_key'])
            linux_client.create_file(self.filename)
            output = linux_client.verify_deamon(self.deamon)
            LOG.info('VSS Deamon is running ${0}'.format(output))
            self.assertIsNotNone(output)
        except Exception:
            LOG.exception('VSS Deamon ' + self.deamon + ' is not running!')
            self._log_console_output()
            raise

    def create_file(self):
        """ Create a file on the vm """
        try:
            linux_client = self.get_remote_client(
                ip_address=self.floating_ip['floatingip']['floating_ip_address'],
                username=self.image_utils.ssh_user(self.image_ref),
                private_key=self.keypair['private_key'])
            linux_client.create_file(self.filename)
            output = linux_client.verify_file(self.filename)
            LOG.info('Created file %s' % output)
            self.assertIsNotNone(output)
        except Exception:
            LOG.exception('Creating file ' + self.filename + ' failed!')
            self._log_console_output()
            raise

    def backup_vm(self):
        """Take a VSS live backup of the VM"""
        cmd = 'powershell -Command ' + self.scriptfolder
        cmd += 'setupscripts\\vss_backup.ps1 -vmName ' + self.instance_name
        cmd += ' -hvServer ' + self.host_name
        cmd += ' -targetDrive ' + self.targetdrive

        wsmancmd = WinRemoteClient(self.host_name, self.username, self.passwd)
        LOG.debug('Sending command %s', cmd)
        try:
            std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd)

        except Exception as exc:
            LOG.exception(exc)
            raise exc

        LOG.info('VSS backup:\nstd_out: %s', std_out)
        LOG.debug('Command std_err: %s', std_err)

        ok = "True" in std_out
        self.assertEqual(ok, True)

    def delete_file(self):
        """ Delete the file from the vm """
        try:
            linux_client = self.get_remote_client(
                ip_address=self.floating_ip['floatingip']['floating_ip_address'],
                username=self.image_utils.ssh_user(self.image_ref),
                private_key=self.keypair['private_key'])
            linux_client.delete_file(self.filename)
            LOG.info('Deleting file from the the VM.')
        except Exception:
            LOG.exception('Cannot delete ' + self.filename)
            self._log_console_output()
            raise

    def restore_vm(self):
        """Restore the VM"""
        cmd = 'powershell -Command ' + self.scriptfolder
        cmd += 'setupscripts\\vss_restore.ps1 -vmName ' + self.instance_name
        cmd += ' -hvServer ' + self.host_name
        cmd += ' -targetDrive ' + self.targetdrive

        wsmancmd = WinRemoteClient(self.host_name, self.username, self.passwd)
        LOG.debug('Sending command %s', cmd)
        # import pdb
        # pdb.set_trace()
        try:
            std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd)
        except Exception as exc:
            LOG.exception(exc)
            raise exc

        LOG.info('VSS restore:\nstd_out: %s', std_out)
        LOG.debug('Command std_err: %s', std_err)

        ok = exit_code == 0
        self.assertEqual(ok, True)

    def verify_file(self):
        """ Verify if the file exists on the vm """
        try:
            linux_client = self.get_remote_client(
                ip_address=self.floating_ip['floatingip']['floating_ip_address'],
                username=self.image_utils.ssh_user(self.image_ref),
                private_key=self.keypair['private_key'])
            output = linux_client.verify_file(self.filename)
            LOG.info('File is present on the VM. ${0}'.format(output))
            self.assertIsNotNone(output)
        except Exception:
            LOG.exception('File ' + self.filename + 'is NOT on the VM!')
            self._log_console_output()
            raise

    @test.services('compute', 'network')
    def test_server_lis_vss_basic(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.boot_instance()
        self.nova_floating_ip_create()
        self.nova_floating_ip_add()
        self.check_vss_deamon()
        self.create_file()
        self.backup_vm()
        self.delete_file()
        self.restore_vm()
        self.verify_file()
        self.servers_client.delete_server(self.instance['id'])
