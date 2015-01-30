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

import base64
import time

from tempest import config
from tempest import exceptions
from tempest import test
from tempest.common.utils import data_utils
from tempest.lis import manager
from tempest.openstack.common import log as logging
from tempest.scenario import utils as test_utils

CONF = config.CONF

LOG = logging.getLogger(__name__)


class Network(manager.LisBase):

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
        self.instances = []
        self.run_ssh = CONF.compute.run_ssh and \
            self.image_utils.is_sshable_image(self.image_ref)
        self.ssh_user = CONF.compute.ssh_user
        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    def add_keypair(self):
        self.keypair = self.create_keypair()

    def boot_instance(self, create_kwargs):
        # Create server with image and flavor from input scenario
        instance = self.create_server(image=self.image_ref,
                                      flavor=self.flavor_ref,
                                      create_kwargs=create_kwargs)
        return instance

    def get_default_network_id(self):
        fixed_network_name = CONF.compute.fixed_network_name
        _, networks = self.networks_client.list_networks()
        if len(networks) > 1:
            for network in networks:
                if network['label'] == fixed_network_name:
                    network_id = network['id']
                    break
            else:
                msg = ("The network on which the NIC of the server must "
                       "be connected can not be found : "
                       "fixed_network_name=%s. Starting instance without "
                       "specifying a network.") % fixed_network_name
                LOG.info(msg)
        return network_id

    def get_default_network(self):
        fixed_network_name = CONF.compute.fixed_network_name
        _, networks = self.networks_client.list_networks()
        if len(networks) > 1:
            for network in networks:
                if network['label'] == fixed_network_name:
                    return network
            else:
                msg = ("The network on which the NIC of the server must "
                       "be connected can not be found : "
                       "fixed_network_name=%s. Starting instance without "
                       "specifying a network.") % fixed_network_name
                LOG.info(msg)

    def nova_floating_ip_create(self):
        _, floating_ip = self.floating_ips_client.create_floating_ip()
        self.addCleanup(self.delete_wrapper,
                        self.floating_ips_client.delete_floating_ip,
                        floating_ip['id'])
        return floating_ip

    def nova_floating_ip_add(self, floating_ip, instance, fixed_address=None):
        if fixed_address:
            self.floating_ips_client.associate_floating_ip_to_address(
                floating_ip['ip'], fixed_address, instance['id'])
        else:
            self.floating_ips_client.associate_floating_ip_to_server(
                floating_ip['ip'], instance['id'])

    def get_default_kwargs(self, user_data=None, networks=None):
        security_groups = [self.security_group]
        create_kwargs = {
            'key_name': self.keypair['name'],
            'security_groups': security_groups
        }

        create_kwargs['networks'] = [{'uuid': self.get_default_network_id()}]
        if networks:
            for net_id in networks:
                create_kwargs['networks'].append({'uuid': net_id})
        if user_data:
            user_data_message = self._get_userdata(user_data)

            create_kwargs['user_data'] = base64.encodestring(user_data_message)
        return create_kwargs

    def _get_userdata(self, user_data):
        if user_data == 'ssh':
            msg = ('#!/bin/sh  \n '
                   'echo "%(content)s" > /home/%(home)s/.ssh/%(name)s;'
                   'chmod 600 /home/%(home)s/.ssh/%(name)s;'
                   'chown %(home)s /home/%(home)s/.ssh/%(name)s;')

        if user_data == 'big_file':
            msg = ('#!/bin/sh  \n '
                   'echo "%(content)s" > /home/%(home)s/.ssh/%(name)s;'
                   'chmod 600 /home/%(home)s/.ssh/%(name)s;'
                   'chown %(home)s /home/%(home)s/.ssh/%(name)s;'
                   'dd if=/dev/urandom of=/tmp/large_file bs=1G count=2;')

        user_data_message = msg % {'home': self.ssh_user,
                                   'content': self.keypair['private_key'],
                                   'name': self.keypair['name']}
        return user_data_message

    def spawn_vm(self, create_kwargs=None):
        fixed_network_name = CONF.compute.fixed_network_name
        self.add_keypair()
        self.security_group = self._create_security_group()
        if not create_kwargs:
            create_kwargs = self.get_default_kwargs()
        instance = self.boot_instance(create_kwargs)
        instance['instance_name'] = instance["OS-EXT-SRV-ATTR:instance_name"]
        instance['host_name'] = instance["OS-EXT-SRV-ATTR:hypervisor_hostname"]
        instance['static_mac'] = instance['addresses'][
            fixed_network_name][0]['OS-EXT-IPS-MAC:mac_addr']
        floating_ip = self.nova_floating_ip_create()
        self.nova_floating_ip_add(floating_ip, instance)
        instance['floating_ip'] = floating_ip
        self.instances.append(instance)

    def spawn_vm_private(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        name = data_utils.rand_name('physnet_private_1_')
        network, snet, router = self.create_networks(phys_net_type=name)
        create_kwargs = self.get_default_kwargs(
            user_data=True, networks=[network['id']])
        for _ in xrange(2):
            instance = self.boot_instance(create_kwargs)
            instance['instance_name'] = instance[
                "OS-EXT-SRV-ATTR:instance_name"]
            instance['host_name'] = instance[
                "OS-EXT-SRV-ATTR:hypervisor_hostname"]
            floating_ip = self.nova_floating_ip_create()
            self.nova_floating_ip_add(floating_ip, instance)
            instance['floating_ip'] = floating_ip
            instance['private_ip'] = instance[
                'addresses'][network['name']][0]['addr']
            instance['private_ip_netmask'] = snet['cidr'].split('/')[1]
            self.instances.append(instance)

    def _spawn_vm(self, create_kwargs):
        instance = self.boot_instance(create_kwargs)
        instance['instance_name'] = instance[
            "OS-EXT-SRV-ATTR:instance_name"]
        instance['host_name'] = instance[
            "OS-EXT-SRV-ATTR:hypervisor_hostname"]
        floating_ip = self.nova_floating_ip_create()
        self.nova_floating_ip_add(floating_ip, instance)
        instance['floating_ip'] = floating_ip
        return instance

    def spawn_vm_bridge(self):
        # get_keys = {'private_ip': "addresses[%s['name']][0]['addr']"} % network
        self.add_keypair()
        self.security_group = self._create_security_group()
        pr1 = data_utils.rand_name('physnet_private_1_')
        pr2 = data_utils.rand_name('physnet_private_2_')
        pr_net_1, pr_snet_1, r = self.create_networks(phys_net_type=pr1)
        pr_net_2, pr_snet_2, r = self.create_networks(phys_net_type=pr2)
        create_kwargs = self.get_default_kwargs(
            user_data=False, networks=[pr_net_1['id']])
        instance = self._spawn_vm(create_kwargs)
        instance['private_ip'] = instance[
            'addresses'][pr_net_1['name']][0]['addr']
        instance['private_ip_netmask'] = pr_snet_1['cidr'].split('/')[1]
        self.instances.append(instance)

        create_kwargs = self.get_default_kwargs(
            user_data=False, networks=[pr_net_1['id'], pr_net_2['id']])
        instance = self._spawn_vm(create_kwargs)
        instance['private_ip_1'] = instance[
            'addresses'][pr_net_1['name']][0]['addr']
        instance['private_ip_netmask_1'] = pr_snet_1['cidr'].split('/')[1]
        instance['private_ip_2'] = instance[
            'addresses'][pr_net_2['name']][0]['addr']
        instance['private_ip_netmask_2'] = pr_snet_2['cidr'].split('/')[1]
        self.instances.append(instance)

        create_kwargs = self.get_default_kwargs(
            user_data=False, networks=[pr_net_2['id']])
        instance = self._spawn_vm(create_kwargs)
        instance['private_ip'] = instance[
            'addresses'][pr_net_2['name']][0]['addr']
        instance['private_ip_netmask'] = pr_snet_2['cidr'].split('/')[1]
        self.instances.append(instance)

    def spawn_double_vm(self, user_datas=None):
        if user_datas:
            vm1_user_data, vm2_user_data = user_datas
        fixed_network_name = CONF.compute.fixed_network_name
        self.add_keypair()
        self.security_group = self._create_security_group()
        for _ in xrange(2):
            if _ == 0:
                create_kwargs = self.get_default_kwargs(
                    user_data=vm1_user_data)
                instance = self.boot_instance(create_kwargs)
            else:
                create_kwargs = self.get_default_kwargs(
                    user_data=vm2_user_data)
                instance = self.boot_instance(create_kwargs)

            instance['instance_name'] = instance[
                "OS-EXT-SRV-ATTR:instance_name"]
            instance['host_name'] = instance[
                "OS-EXT-SRV-ATTR:hypervisor_hostname"]
            floating_ip = self.nova_floating_ip_create()
            self.nova_floating_ip_add(floating_ip, instance)
            instance['floating_ip'] = floating_ip
            instance['private_ip'] = instance[
                'addresses'][fixed_network_name][0]['addr']
            self.instances.append(instance)

    def spawn_vm_multi_nic(self):
        self.add_keypair()
        self.security_group = self._create_security_group()
        network, snet, router = self.create_networks()
        create_kwargs = self.get_default_kwargs(
            user_data=False, networks=[network['id']])
        instance = self.boot_instance(create_kwargs)
        instance['instance_name'] = instance["OS-EXT-SRV-ATTR:instance_name"]
        instance['host_name'] = instance["OS-EXT-SRV-ATTR:hypervisor_hostname"]
        floating_ip = self.nova_floating_ip_create()
        self.nova_floating_ip_add(floating_ip, instance)
        instance['floating_ip'] = floating_ip
        instance['snet_gateway_ip'] = snet['gateway_ip']
        self.instances.append(instance)

    def set_ip(self, ip, netmask, interface, linux_client=None):
        if linux_client:
            linux_client.set_ip(ip, netmask, interface)
        else:
            self.linux_client.set_ip(ip, netmask, interface)

    def verify_ping(self, destination, interface='eth0', linux_client=None):
        if linux_client:
            linux_client.ping_host(destination, interface)
        else:
            self.linux_client.ping_host(destination)

    def check_mac(self, expected_mac, linux_client=None):
        if linux_client:
            linux_client.check_mac_match(expected_mac)
        else:
            self.linux_client.check_mac_match(expected_mac)

    def check_nic_operstate(self, linux_client=None):
        if linux_client:
            self.check_operstate(linux_client)
        else:
            self.check_operstate(self.linux_client)

    def check_network_mode(self, linux_client=None):
        if linux_client:
            linux_client.set_promisc()
            linux_client.check_promisc()
        else:
            self.linux_client.set_promisc()
            self.linux_client.check_promisc()

    def wait_big_disk(self, linux_client):
        log_path = '/var/log/cloud-init-output.log'
        log_message = 'copied'
        error_message = 'Failed running'
        _start_time = time.time()
        timeout = 300
        while True:
            finished_script = linux_client.check_log(log_path, log_message)
            fail = linux_client.check_log(log_path, error_message)
            self.assertFalse(fail, 'Failed to run cloud-init script on vm')
            if finished_script:
                break
            if self._is_timed_out(_start_time, timeout):
                LOG.exception("Failed to retrieve cloud-init status"
                              " connection to %s@%s after %d seconds",
                              self.ssh_user, linux_client.ssh_client.host, timeout)
                raise exceptions.SSHTimeout()
            time.sleep(30)

    def _is_timed_out(self, start_time, timeout):
        return (time.time() - timeout) > start_time

    def set_legacy(self, linux_client=None):
        network = self.get_default_network()
        port = self._create_port(network)
        snet_id = port['fixed_ips'][0]['subnet_id']
        snet = self.get_subnet(snet_id)
        ip = port['fixed_ips'][0]['ip_address']
        gateway = snet['gateway_ip']
        netmask = snet['cidr'].split('/')[1]
        if linux_client:
            linux_client.set_legacy_adapter(ip, netmask, gateway)
        else:
            self.linux_client.set_legacy_adapter(ip, netmask, gateway)

    def _initiate_linux_client(self, server_or_ip, username, private_key):
        try:
            return self.get_remote_client(
                server_or_ip=server_or_ip,
                username=username,
                private_key=private_key)
        except Exception as exc:
            LOG.exception(exc)
            self._log_console_output()
            raise exc

    def set_mac_spoofing(self, vm):
        self.host_client.run_powershell_cmd(
            'Set-VMNetworkAdapter',
            ComputerName=vm2['host_name'],
            VMName=vm2['instance_name'],
            MacAddressSpoofing='on')

    def _set_bridge(self, linux_client, static_ip, netmask, dev1, dev2):
        script = 'SetBridge.sh'
        cmd = './{script} {ip} {netmask} {dev1} {dev2}'.format(
            script=script,
            ip=static_ip,
            netmask=netmask,
            dev1=dev1,
            dev2=dev2)

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_bridge_network(self):
        self.spawn_vm_bridge()
        vm1 = self.instances[0]
        vm2 = self.instances[1]
        vm3 = self.instances[1]
        self.stop_vm(vm2['id'])
        # self._initiate_host_client(vm2['host_name'])
        # self.set_mac_spoofing(vm2])
        # self.start_vm(vm2['id'])
        # vm1_lin_clt = self._initiate_linux_client(vm1['floating_ip']['ip'],
        #                                           self.ssh_user, self.keypair['private_key'])
        # self.set_ip(ip=vm1['private_ip'], netmask=vm1['private_ip_netmask'],
        #             interface='eth1', linux_client=vm1_lin_clt)
        # vm2_lin_clt = self._initiate_linux_client(vm2['floating_ip']['ip'],
        #                                           self.ssh_user, self.keypair['private_key'])
        # self.set_ip(ip=vm2['private_ip_1'], netmask=vm2['private_ip_netmask_1'],
        #             interface='eth1', linux_client=vm2_lin_clt)
        # self.set_ip(ip=vm2['private_ip_2'], netmask=vm2['private_ip_netmask_2'],
        #             interface='eth2', linux_client=vm2_lin_clt)
        # _create_port_from_network()
        # self._set_bridge(vm2_lin_clt, _extra_port, vm2['private_ip_netmask_2'], 'eth1', 'eth2')
        # vm3_lin_clt = self._initiate_linux_client(vm3['floating_ip']['ip'],
        #                                           self.ssh_user, self.keypair['private_key'])
        # self.set_ip(ip=vm3['private_ip'], netmask=vm3['private_ip_netmask'],
        #             interface='eth1', linux_client=vm3_lin_clt)
        # self.verify_ping(
        # destination=vm1['private_ip'], interface='eth1',
        # linux_client=vm2_lin_clt)

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_external_network(self):
        self.spawn_vm()
        self.linux_client = self._initiate_linux_client(self.instances[0]['floating_ip']['ip'],
                                                        self.ssh_user, self.keypair['private_key'])
        self.verify_ping('8.8.8.8')

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_private_network(self):
        self.spawn_vm_private()
        vm1 = self.instances[0]
        vm2 = self.instances[1]
        vm1_lin_clt = self._initiate_linux_client(vm1['floating_ip']['ip'],
                                                  self.ssh_user, self.keypair['private_key'])
        self.set_ip(ip=vm1['private_ip'], netmask=vm1['private_ip_netmask'],
                    interface='eth1', linux_client=vm1_lin_clt)
        vm2_lin_clt = self._initiate_linux_client(vm2['floating_ip']['ip'],
                                                  self.ssh_user, self.keypair['private_key'])
        self.set_ip(ip=vm2['private_ip'], netmask=vm2['private_ip_netmask'],
                    interface='eth1', linux_client=vm2_lin_clt)
        self.verify_ping(
            destination=vm1['private_ip'], interface='eth1', linux_client=vm2_lin_clt)

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_copy_large_file(self):
        user_datas = ('big_file', 'ssh')
        self.spawn_double_vm()
        vm1 = self.instances[0]
        vm2 = self.instances[1]
        vm1_lin_clt = self._initiate_linux_client(vm1['floating_ip']['ip'],
                                                  self.ssh_user, self.keypair['private_key'])
        vm2_lin_clt = self._initiate_linux_client(vm2['floating_ip']['ip'],
                                                  self.ssh_user, self.keypair['private_key'])
        self.wait_big_disk(vm1_lin_clt)
        self.copy_over(
            linux_client=vm1_lin_clt, ip_destination=vm2['private_ip'], user=self.ssh_user)

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_multiple_networks(self):
        self.spawn_vm_multi_nic()
        vm1 = self.instances[0]
        vm1_lin_clt = self._initiate_linux_client(vm1['floating_ip']['ip'],
                                                  self.ssh_user, self.keypair['private_key'])
        self.verify_ping(
            destination='8.8.8.8', interface='eth0', linux_client=vm1_lin_clt)
        vm1_lin_clt.refresh_iface('eth1')
        self.verify_ping(destination=vm1['snet_gateway_ip'],
                         interface='eth1', linux_client=vm1_lin_clt)

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_static_mac(self):
        self.spawn_vm()
        self.linux_client = self._initiate_linux_client(self.instances[0]['floating_ip']['ip'],
                                                        self.ssh_user, self.keypair['private_key'])
        vm = self.instances[0]
        self.check_mac(vm['static_mac'])

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_network_mode(self):
        self.spawn_vm()
        self.linux_client = self._initiate_linux_client(self.instances[0]['floating_ip']['ip'],
                                                        self.ssh_user, self.keypair['private_key'])
        vm = self.instances[0]
        self.check_network_mode()

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_network_legacy(self):
        self.spawn_vm()
        vm = self.instances[0]
        self.linux_client = self._initiate_linux_client(vm['floating_ip']['ip'],
                                                        self.ssh_user, self.keypair['private_key'])
        self._initiate_host_client(vm['host_name'])
        self.stop_vm(vm['id'])
        self.add_legacy_nic(vm['instance_name'], vm['host_name'])
        self.start_vm(vm['id'])
        self.linux_client.validate_authentication()
        self.set_legacy()

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_operstate(self):
        self.spawn_vm()
        self.linux_client = self._initiate_linux_client(self.instances[0]['floating_ip']['ip'],
                                                        self.ssh_user, self.keypair['private_key'])
        vm = self.instances[0]
        self._initiate_host_client(vm['host_name'])
        self.stop_vm(vm['id'])
        self.add_empty_nic(vm['instance_name'], vm['host_name'])
        self.start_vm(vm['id'])
        self.linux_client.validate_authentication()
        self.check_nic_operstate()
