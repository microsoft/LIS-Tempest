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
from tempest.common import waiters
from tempest import config
from oslo_log import log as logging
from tempest.lis import manager
from tempest.scenario import utils as test_utils
from tempest import test

CONF = config.CONF

LOG = logging.getLogger(__name__)


class KVP(manager.LisBase):

    def setUp(self):
        super(KVP, self).setUp()
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
        self.deamon = "'[h]v_kvp_daemon\|[h]ypervkvpd'"
        self.run_ssh = CONF.validation.run_validation and \
            self.image_utils.is_sshable_image(self.image_ref)
        self.ssh_user = CONF.validation.image_ssh_user
        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    @test.attr(type=['smoke', 'core', 'kvp'])
    @test.services('compute', 'network')
    def test_kvp_basic(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.verify_lis(self.instance_name, "'Key-Value Pair Exchange'")
        """ Check if KVP runs on the vm """
        try:
            output = self.linux_client.verify_deamon(self.deamon)
            LOG.info('KVP Deamon is running ${0}'.format(output))
            self.assertIsNotNone(output)
        except Exception:
            LOG.exception('KVP Deamon ' + self.deamon + ' is not running!')
            self._log_console_output()
            raise
        self.check_kvp_basic(self.instance_name)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'core', 'kvp'])
    @test.services('compute', 'network')
    def test_kvp_add_Key_Values(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.verify_lis(self.instance_name, "'Key-Value Pair Exchange'")
        self.send_kvp_client()
        self.kvp_add_value(self.instance_name)
        self.linux_client.kvp_verify_value()
        self.servers_client.delete_server(self.instance['id'])