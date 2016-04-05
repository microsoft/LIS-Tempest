# Copyright 2014 Cloudbase Solutions Srl
# All rights reserved
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
import os

from tempest import config
from tempest import exceptions
from tempest import test
#from tempest.common import debug
from tempest.common.utils.windows.remote_client import WinRemoteClient
from tempest.lis import manager
from oslo_log import log as logging
from tempest.scenario import utils as test_utils

CONF = config.CONF

LOG = logging.getLogger(__name__)

MAXIMUM_DELAY = 7   #7 seconds
SLEEP_TIME = 600    #600 seconds


class TimeSync(manager.LisBase):

    def setUp(self):
        super(TimeSync, self).setUp()
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
        self.run_ssh = CONF.compute.run_ssh and \
            self.image_utils.is_sshable_image(self.image_ref)
        self.ssh_user = CONF.validation.image_ssh_user
        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    def add_keypair(self):
        self.keypair = self.create_keypair()

    def boot_instance(self):
        # Create server with image and flavor from input scenario
        security_groups = [self.security_group]
    	self.instance = self.create_server(flavor=self.flavor_ref,
                	                   image_id=self.image_ref,
                        	           key_name=self.keypair['name'],
                                	   security_groups=security_groups,
                                   	   wait_until='ACTIVE')
        self.instance_name = self.instance["OS-EXT-SRV-ATTR:instance_name"]
        self.host_name = self.instance["OS-EXT-SRV-ATTR:hypervisor_hostname"]
        self._initiate_host_client(self.host_name)

    def nova_floating_ip_create(self):
    	floating_network_id = CONF.network.public_network_id
    	self.floating_ip = self.floating_ips_client.create_floatingip(floating_network_id=floating_network_id)
    	self.addCleanup(self.delete_wrapper,
            	self.floating_ips_client.delete_floatingip,
            	self.floating_ip['floatingip']['floating_ip_address'])

    def nova_floating_ip_add(self):
    	self.compute_floating_ips_client.associate_floating_ip_to_server(
    	   self.floating_ip['floatingip']['floating_ip_address'], self.instance['id'])

    def spawn_vm(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.boot_instance()
        self.nova_floating_ip_create()
        self.nova_floating_ip_add()
        self.server_id = self.instance['id']

    def check_ntp_time(self):
        try:
            script_name = 'CORE_timesync_NTP.sh'
            script_path = '/scripts/' + script_name
            destination = '/tmp/'
            my_path = os.path.abspath(
                os.path.normpath(os.path.dirname(__file__)))
            full_script_path = my_path + script_path
            cmd_params = []
            self.linux_client.execute_script(
                script_name, cmd_params, full_script_path, destination)

        except exceptions.SSHExecCommandFailed as exc:

            LOG.exception(exc)
            self._log_console_output()
            raise exc

        except Exception as exc:
            LOG.exception(exc)
            self._log_console_output()
            raise exc

    @test.attr(type=['smoke', 'core', 'timesync'])
    @test.services('compute', 'network')
    def test_time_sync_ntp(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.check_ntp_time()
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'core', 'timesync'])
    @test.services('compute', 'network')
    def test_time_sync_host(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        vm_time = self.get_vm_time()
        t0 = time.time()
        host_time = self.get_host_time()
        t1 = time.time()
        exec_time = t1 - t0
        LOG.debug('Duration of get_host_time %s', exec_time)
        self.assertTrue(abs(vm_time - host_time) - exec_time < MAXIMUM_DELAY)
        self.servers_client.delete_server(self.instance['id'])

    @test.attr(type=['smoke', 'core', 'timesync'])
    @test.services('compute', 'network')
    def test_time_sync_saved_state(self):
        self.spawn_vm()
        self._initiate_linux_client(self.floating_ip['floatingip']['floating_ip_address'],
                                    self.ssh_user, self.keypair['private_key'])
        self.save_vm(self.server_id)
        time.sleep(SLEEP_TIME)
        self.unsave_vm(self.server_id)
        vm_time = self.get_vm_time()
        t0 = time.time()
        host_time = self.get_host_time()
        t1 = time.time()
        exec_time = t1 - t0
        LOG.debug('Duration of get_host_time %s', exec_time)
        self.assertTrue(abs(vm_time - host_time) - exec_time < MAXIMUM_DELAY)
        self.servers_client.delete_server(self.instance['id'])
