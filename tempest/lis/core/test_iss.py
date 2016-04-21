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
from tempest import exceptions
from tempest import test
from oslo_log import log as logging
from tempest.lis import manager
from tempest.scenario import utils as test_utils

CONF = config.CONF

LOG = logging.getLogger(__name__)


class ISS(manager.LisBase):

    def setUp(self):
        super(ISS, self).setUp()
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

    def _verify_integrated_shutdown_services(self):
        status = self.verify_lis(self.instance_name, 'Shutdown')
        self.assertTrue('true' == status,
                        "Integrated shutdown services disabled.")
        self.disable_lis(self.instance_name, 'Shutdown')
        status = self.verify_lis(self.instance_name, 'Shutdown')
        self.assertTrue('false' == status, 'Failed to disable iss.')
        self.enable_lis(self.instance_name, 'Shutdown')
        status = self.verify_lis(self.instance_name, 'Shutdown')
        self.assertTrue('true' == status, 'Failed to enable iss.')

    @test.attr(type=['smoke', 'core', 'iss'])
    @test.services('compute', 'network')
    def test_iss(self):
        self.spawn_vm()
        self.stop_vm(self.server_id)
        self.start_vm(self.server_id)
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        try:
            self.linux_client.ping_host('127.0.0.1')

        except exceptions.SSHExecCommandFailed as exc:
            LOG.exception(exc)
            raise exc

    @test.attr(type=['core', 'iss'])
    @test.services('compute', 'network')
    def test_iss_reload(self):
        self.spawn_vm()
        self._verify_integrated_shutdown_services()
