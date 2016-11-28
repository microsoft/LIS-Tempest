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


import re

from oslo_log import log as logging
from tempest import config, test
from tempest.lis import manager
from tempest.scenario import utils as test_utils

CONF = config.CONF

LOG = logging.getLogger(__name__)


class Clocksource(manager.LisBase):

    def setUp(self):
        super(Clocksource, self).setUp()
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

    def check_clocksource(self, linux_client):
        self.stop_vm(self.server_id)
        self.start_vm(self.server_id)

        try:
            linux_client = self.get_remote_client(
                self.floating_ip['floatingip']['floating_ip_address'],
                self.ssh_user, self.keypair['private_key'])

            check_file = linux_client.exec_command('find /sys/devices/system/clocksource/clocksource0/current_clocksource -type f -size +0M')
            self.assertTrue(check_file != "",
                            "Test Failed. No file was found current_clocksource greater than 0M")

            file_name = linux_client.exec_command('cat /sys/devices/system/clocksource/clocksource0/current_clocksource')
            result = re.search("hyperv_clocksource", file_name)
            self.assertTrue(result is not None,
                            "Proper file was not found.")

        except Exception:
            LOG.exception('ssh to server failed')
            self._log_console_output()
            raise

        LOG.info('Test passed: the current_clocksource is not null and value is right.')

    @test.attr(type=['core', 'clock'])
    @test.services('compute', 'network')
    def test_check_clocksource(self):
        """This function checks if the hyperv_clocksource file exists on the VM."""

        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_clocksource(self.linux_client)
        self.servers_client.delete_server(self.instance['id'])
