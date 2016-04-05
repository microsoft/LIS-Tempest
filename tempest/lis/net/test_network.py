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
import netaddr
import os
from tempest import config
from tempest.common.utils import data_utils
from tempest.common.utils.windows.remote_client import WinRemoteClient
from tempest.lis import manager
from oslo_log import log as logging
from tempest.scenario import utils as test_utils
from tempest import test
import pdb

CONF = config.CONF

LOG = logging.getLogger(__name__)

load_tests = test_utils.load_tests_input_scenario_utils


class Network(manager.ScenarioTest):

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
        super(Network, self).setUp()
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
        self.run_ssh = CONF.compute.run_ssh and \
            self.image_utils.is_sshable_image(self.image_ref)
        self.ssh_user = self.image_utils.ssh_user(self.image_ref)
        self.host_username = CONF.host_credentials.host_user_name
        self.host_password = CONF.host_credentials.host_password
        self.scriptfolder = CONF.host_credentials.host_setupscripts_folder
        self.lis_private_network = CONF.lis.private_network

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
        self._initiate_wsman(self.host_name)

    def _initiate_wsman(self, host_name):
        try:
            self.wsmancmd = WinRemoteClient(
                host_name, self.host_username, self.host_password)

        except Exception as exc:
            LOG.exception(exc)
            raise exc

    def nova_floating_ip_create(self):
        _, self.floating_ip = self.floating_ips_client.create_floating_ip()
        self.addCleanup(self.delete_wrapper,
                        self.floating_ips_client.delete_floating_ip,
                        self.floating_ip['id'])

    def nova_floating_ip_add(self):
    	self.compute_floating_ips_client.associate_floating_ip_to_server(
    	   self.floating_ip['floatingip']['floating_ip_address'], self.instance['id'])

    def verify_ssh(self):
        if self.run_ssh:
            # Obtain a floating IP
            _, floating_ip = self.floating_ips_client.create_floating_ip()
            self.addCleanup(self.delete_wrapper,
                            self.floating_ips_client.delete_floating_ip,
                            floating_ip['id'])
            # Attach a floating IP
            self.floating_ips_client.associate_floating_ip_to_server(
                floating_ip['ip'], self.instance['id'])
            # Check ssh
            try:
                self.get_remote_client(
                    server_or_ip=floating_ip['ip'],
                    username=self.image_utils.ssh_user(self.image_ref),
                    private_key=self.keypair['private_key'])
            except Exception:
                LOG.exception('ssh to server failed')
                self._log_console_output()
                raise

    def verify_external_ping(self, destination_ip):
        if self.run_ssh:
            # Obtain a floating IP
            _, floating_ip = self.floating_ips_client.create_floating_ip()
            self.addCleanup(self.delete_wrapper,
                            self.floating_ips_client.delete_floating_ip,
                            floating_ip['id'])
            # Attach a floating IP
            self.floating_ips_client.associate_floating_ip_to_server(
                floating_ip['ip'], self.instance['id'])
            # Check lis presence
            try:
                linux_client = self.get_remote_client(
                    server_or_ip=floating_ip['ip'],
                    username=self.image_utils.ssh_user(self.image_ref),
                    private_key=self.keypair['private_key'])

                output = linux_client.verify_ping(destination_ip)
                LOG.info('Ping resuls', output)
                self.assertNotEqual(0, output)
            except Exception:
                LOG.exception('ssh to server failed')
                self._log_console_output()
                raise


class Basic(Network):

    def setUp(self):
        super(Basic, self).setUp()

    @test.services('compute', 'network')
    def test_configure_network(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.boot_instance()
        self.verify_ssh()
        self.servers_client.delete_server(self.instance['id'])

    @test.services('compute', 'network')
    def test_external_network(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.boot_instance()
        self.verify_external_ping('8.8.8.8')
        self.servers_client.delete_server(self.instance['id'])


class Bridge(Network):

    def setUp(self):
        super(Bridge, self).setUp()
        self.instances = []
        self.floating_ips = []

    def boot_instances(self, count=1):
        # Create server with image and flavor from input scenario
        security_groups = [self.security_group]
        create_kwargs = {
            'key_name': self.keypair['name'],
            'security_groups': security_groups
        }
        for _ in range(count):
            instance = self.create_server(image=self.image_ref,
                                          flavor=self.flavor_ref,
                                          create_kwargs=create_kwargs)
            instance['instance_name'] = instance[
                "OS-EXT-SRV-ATTR:instance_name"]
            floating_ip = self.nova_floating_ip_create()
            self.nova_floating_ip_add(floating_ip, instance)
            instance['floating_ip'] = floating_ip
            self.instances.append(instance)

        self.host_name = instance["OS-EXT-SRV-ATTR:hypervisor_hostname"]

    def _initiate_wsman(self, host_name):
        try:
            self.wsmancmd = WinRemoteClient(
                host_name, self.host_username, self.host_password)

        except Exception as exc:
            LOG.exception(exc)
            raise exc

    def nova_floating_ip_create(self):
        _, floating_ip = self.floating_ips_client.create_floating_ip()
        self.addCleanup(self.delete_wrapper,
                        self.floating_ips_client.delete_floating_ip,
                        floating_ip['id'])
        return floating_ip

    def nova_floating_ip_add(self, floating_ip, instance):
        self.floating_ips_client.associate_floating_ip_to_server(
            floating_ip['ip'], instance['id'])

    def send_command(self, cmd):

        LOG.debug('Sending command %s', cmd)
        try:

            std_out, std_err, exit_code = self.wsmancmd.run_wsman_cmd(cmd)
        except Exception as exc:
            LOG.exception(exc)
            raise exc

        LOG.info('Add disk:\nstd_out: %s', std_out)
        LOG.debug('Command std_err: %s', std_err)
        self.assertFalse(exit_code != 0)

    def refresh_repo(self):
        cmd = 'powershell cd ' + self.scriptfolder
        cmd += '; git pull'
        self.send_command(cmd)

    def configure_switches(self):
        """Create/attach vswitches to VMs"""
        pr_switch = data_utils.rand_name(self.__class__.__name__)
        cmd = 'powershell ' + self.scriptfolder
        cmd += 'setupscripts\\create-private-vSwitch.ps1'
        cmd += ' -baseName ' + pr_switch
        self.send_command(cmd)
        self.addCleanup(self.delete_temp_switches, pr_switch)

        cmd = 'powershell ' + self.scriptfolder
        cmd += 'setupscripts\\bridge_setup.ps1'
        cmd += ' -baseName ' + pr_switch
        cmd += ' -vm1 ' + self.vm1['instance_name']
        cmd += ' -vm2 ' + self.vm2['instance_name']
        cmd += ' -vm3 ' + self.vm3['instance_name']
        self.send_command(cmd)

    def delete_temp_switches(self, pr_switch):
        """Create/attach vswitches to VMs"""
        cmd = 'powershell ' + self.scriptfolder
        cmd += 'setupscripts\\delete-private-vSwitch.ps1'
        cmd += ' -baseName ' + pr_switch

        self.send_command(cmd)

    def setup_bridge_env(self):
        """TODO: get device dynamically based on macaddr"""
        network = netaddr.IPNetwork(self.lis_private_network)
        broadcast = netaddr.IPAddress(network.first + 1)
        prefix = network.prefixlen

        self.vm1['static_ip'] = broadcast + 1
        self.vm1['static_device'] = 'eth1'
        self.vm3['static_ip'] = broadcast + 2
        self.vm3['static_device'] = 'eth1'

        self._set_interfaces(
            self.vm1, self.vm1['static_ip'], prefix, self.vm1['static_device'])
        self._set_interfaces(
            self.vm3, self.vm3['static_ip'], prefix, self.vm3['static_device'])
        self._set_bridge(self.vm2, broadcast + 3, prefix, 'eth1', 'eth2')

    def _set_bridge(self, vm, static_ip, netmask, dev1, dev2):
        try:
            linux_client = self.get_remote_client(
                server_or_ip=vm['floating_ip']['ip'],
                username=self.image_utils.ssh_user(self.image_ref),
                private_key=self.keypair['private_key'])
            script = 'SetBridge.sh'
            cmd = './{script} {ip} {netmask} {dev1} {dev2}'.format(
                script=script,
                ip=static_ip,
                netmask=netmask,
                dev1=dev1,
                dev2=dev2)
            MY_PATH = os.path.abspath(
                os.path.normpath(os.path.dirname(__file__)))

            copy_file = linux_client.copy_over(
                MY_PATH + '/scripts/' + script, '/root/')
            output = linux_client.ssh_client.exec_command(
                'cd /root/; dos2unix ' + script)
            output = linux_client.ssh_client.exec_command('chmod +x ' + script)
            output = linux_client.ssh_client.exec_command(cmd)

        except Exception as exc:
            output = linux_client.ssh_client.exec_command(
                'cat ~/{script}.log'.format(script=script))
            LOG.exception('Inside logs for failure: %s' % output)
            LOG.exception(exc)
            self._log_console_output()
            raise exc

    def _set_interfaces(self, vm, static_ip, netmask, device):
        try:
            linux_client = self.get_remote_client(
                server_or_ip=vm['floating_ip']['ip'],
                username=self.image_utils.ssh_user(self.image_ref),
                private_key=self.keypair['private_key'])
            script = 'SetStaticIp.sh'
            cmd = './{script} {ip} {netmask} {dev}'.format(
                script=script,
                ip=static_ip,
                netmask=netmask,
                dev=device)
            MY_PATH = os.path.abspath(
                os.path.normpath(os.path.dirname(__file__)))

            copy_file = linux_client.copy_over(
                MY_PATH + '/scripts/' + script, '/root/')
            output = linux_client.ssh_client.exec_command(
                'cd /root/; dos2unix ' + script)
            output = linux_client.ssh_client.exec_command('chmod +x ' + script)
            output = linux_client.ssh_client.exec_command(cmd)

        except Exception as exc:
            output = linux_client.ssh_client.exec_command(
                'cat ~/{script}.log'.format(script=script))
            LOG.exception('Inside logs for failure: %s' % output)
            LOG.exception(exc)
            self._log_console_output()
            raise exc

    def verify_pings(self):
        self._test_ping(
            self.vm1, self.vm1['static_device'], self.vm3['static_ip'])
        self._test_ping(
            self.vm3, self.vm3['static_device'], self.vm1['static_ip'])

    def _test_ping(self, vm, device, target):
        try:
            linux_client = self.get_remote_client(
                server_or_ip=vm['floating_ip']['ip'],
                username=self.image_utils.ssh_user(self.image_ref),
                private_key=self.keypair['private_key'])

            output = linux_client.verify_ping(target, device)
            LOG.info('Ping result %s', output)
            self.assertNotEqual(0, output)

        except Exception as exc:
            LOG.exception(exc)
            self._log_console_output()
            raise exc

    def stop_instances(self):
        for instance in self.instances:
            self.servers_client.stop(instance['id'])
        for instance in self.instances:
            self.servers_client.wait_for_server_status(
                instance['id'], 'SHUTOFF')

    def start_instances(self):
        for instance in self.instances:
            self.servers_client.start(instance['id'])
        for instance in self.instances:
            self.servers_client.wait_for_server_status(
                instance['id'], 'ACTIVE')

    def delete_servers(self):
        for instance in self.instances:
            self.servers_client.delete_server(instance['id'])

    @test.services('compute', 'network')
    def test_bridge_private(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        self.boot_instances(3)
        self._initiate_wsman(self.host_name)
        self.refresh_repo()
        self.stop_instances()
        self.vm1 = self.instances[0]
        self.vm2 = self.instances[1]
        self.vm3 = self.instances[2]
        """attach vsiwtches/set-promisc"""
        self.configure_switches()
        self.start_instances()
        """configure bridge"""
        self.setup_bridge_env()
        """test pings from one another"""
        self.verify_pings()
        self.delete_servers()
