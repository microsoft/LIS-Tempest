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
from tempest import exceptions
from tempest import test
from tempest.common.utils import data_utils
from tempest.lis import manager
from oslo_log import log as logging
from tempest.scenario import utils as test_utils
import time

CONF = config.CONF

LOG = logging.getLogger(__name__)


class Reboot(manager.LisBase):

    def setUp(self):
        super(Reboot, self).setUp()
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

    def create_flavor(self, new_ram):
        _, c_f = self.flavor_client.get_flavor_details(self.flavor_ref)
        self.assertEqual(_.status, 200)
        name = data_utils.rand_name('flavor')
        f_id = data_utils.rand_int_id(start=1000)
        _, new_f = self.flavor_client.create_flavor(name=name, ram=new_ram, vcpus=int(
            c_f['vcpus']), disk=int(c_f['disk']), flavor_id=f_id)
        self.assertEqual(_.status, 200)
        self.addCleanup(self.flavor_client.delete_flavor, new_f['id'])
        return new_f['id']

    def _test_reboot_native(self, mem_settings):
        """ Currently resize failing """
        for memory in mem_settings:
            new_flavor = self.create_flavor(memory)
            self.servers_client.resize(self.server_id, new_flavor)
            waiters.wait_for_server_status(self.servers_client, self.server_id,
                                                       'VERIFY_RESIZE')
            self.servers_client.confirm_resize(self.server_id)
            self.servers_client.reboot(self.server_id, 'SOFT')
            self._wait_for_server_status('ACTIVE')

    def _test_reboot(self, mem_settings):
        for memory in mem_settings:
            self.stop_vm(self.server_id)
            self.set_ram_settings(self.instance_name, memory)
            self.start_vm(self.server_id)
            try:
                self.linux_client.ping_host('127.0.0.1')

            except exceptions.SSHExecCommandFailed as exc:
                LOG.exception(exc)
                raise exc

    @test.attr(type=['core'])
    @test.services('compute', 'network')
    def test_reboot_various_mem(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        """
        Get back to this approach once resize is fixed
        mem_settings = [2048, 3584, 4608, 6144]
        self._test_reboot_native(mem_settings)
        """
        mem_settings = [2048, 3584, 4608]
        self._test_reboot(mem_settings)
