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
        self.instances = []
        self.run_ssh = CONF.compute.run_ssh and \
            self.image_utils.is_sshable_image(self.image_ref)
        self.ssh_user = CONF.compute.ssh_user
        LOG.debug('Starting test for image:{image}, flavor:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))
        self.user_data_base = {
            'ssh': ('#!/bin/sh  \n '
                    'echo "%(content)s" > /home/%(home)s/.ssh/%(name)s;'
                    'chmod 600 /home/%(home)s/.ssh/%(name)s;'
                    'chown %(home)s /home/%(home)s/.ssh/%(name)s;'),
            'big_file': ('#!/bin/sh  \n '
                         'echo "%(content)s" > /home/%(home)s/.ssh/%(name)s;'
                         'chmod 600 /home/%(home)s/.ssh/%(name)s;'
                         'chown %(home)s /home/%(home)s/.ssh/%(name)s;'
                         'dd if=/dev/urandom of=/tmp/large_file '
                         'bs=1G count=%(gb_count)i;')
        }

    def add_keypair(self):
        self.keypair = self.create_keypair()

    def boot_instance(self, create_kwargs):
        # Create server with image and flavor from input scenario
        instance = self.create_server(image=self.image_ref,
                                      flavor=self.flavor_ref,
                                      create_kwargs=create_kwargs)
        return instance

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

    def nova_floating_ip_add(self, floating_ip, instance):
        self.floating_ips_client.associate_floating_ip_to_server(
            floating_ip['ip'], instance['id'])

    def get_default_kwargs(self, user_data=None, networks=None):
        security_groups = [self.security_group]
        create_kwargs = {
            'key_name': self.keypair['name'],
            'security_groups': security_groups
        }
        net = self.get_default_network()
        create_kwargs['networks'] = [{'uuid': net['id']}]
        if networks:
            for net_id in networks:
                create_kwargs['networks'].append({'uuid': net_id})
        if user_data:
            encrypted_user_data = self._get_userdata(user_data)
            create_kwargs['user_data'] = encrypted_user_data
        return create_kwargs

    def _get_userdata(self, user_data):
        file_size = CONF.lis_specific.copy_large_file_size
        key = self.keypair['private_key']
        msg = self.user_data_base[user_data]
        user_data_message = msg % {'home': self.ssh_user,
                                   'content': key,
                                   'name': self.keypair['name'],
                                   'gb_count': file_size}
        return base64.encodestring(user_data_message)

    def _spawn_vm(self, create_kwargs):
        fixed_network_name = CONF.compute.fixed_network_name
        instance = self.boot_instance(create_kwargs)
        instance['instance_name'] = instance[
            "OS-EXT-SRV-ATTR:instance_name"]
        instance['host_name'] = instance[
            "OS-EXT-SRV-ATTR:hypervisor_hostname"]
        floating_ip = self.nova_floating_ip_create()
        self.nova_floating_ip_add(floating_ip, instance)
        instance['floating_ip'] = floating_ip['ip']
        return instance

    def spawn_vm_basic(self, mac=False):
        fixed_network_name = CONF.compute.fixed_network_name
        self.add_keypair()
        self.security_group = self._create_security_group()
        create_kwargs = self.get_default_kwargs()
        instance = self._spawn_vm(create_kwargs)
        if mac:
            instance['static_mac'] = instance['addresses'][
                fixed_network_name][0]['OS-EXT-IPS-MAC:mac_addr']
        return instance

    def spawn_vm_multi_nic(self):
        fixed_network_name = CONF.compute.fixed_network_name
        self.add_keypair()
        self.security_group = self._create_security_group()
        network, snet, router = self.create_networks()
        create_kwargs = self.get_default_kwargs(
            user_data=None, networks=[network['id']])
        instance = self._spawn_vm(create_kwargs)
        instance['gateway_2'] = snet['gateway_ip']
        instance['mac_1'] = instance['addresses'][
            fixed_network_name][0]['OS-EXT-IPS-MAC:mac_addr']
        instance['mac_2'] = instance['addresses'][
            network['name']][0]['OS-EXT-IPS-MAC:mac_addr']
        return instance

    def spawn_vm_private(self):
        private = CONF.lis_specific.phys_private_1
        self.add_keypair()
        self.security_group = self._create_security_group()
        name = data_utils.rand_name(private)
        network, snet, router = self.create_networks(phys_net_type=name)
        create_kwargs = self.get_default_kwargs(
            user_data=None, networks=[network['id']])
        for _ in xrange(2):
            instance = self._spawn_vm(create_kwargs)
            netw = instance['addresses'][network['name']][0]
            instance['private_ip'] = netw['addr']
            instance['private_mac'] = netw['OS-EXT-IPS-MAC:mac_addr']
            instance['private_ip_netmask'] = snet['cidr'].split('/')[1]
            self.instances.append(instance)

    def spawn_vm_bridge(self):
        private = CONF.lis_specific.phys_private_1
        private_2 = CONF.lis_specific.phys_private_2
        self.add_keypair()
        self.security_group = self._create_security_group()
        pr1 = data_utils.rand_name(private)
        pr2 = data_utils.rand_name(private_2)
        pr_net_1, pr_snet_1, r = self.create_networks(phys_net_type=pr1)
        pr_net_2, pr_snet_2, r = self.create_networks(
            phys_net_type=pr2, existing_cidr=pr_snet_1['cidr'])
        self.bridge_network = pr_net_1

        create_kwargs = self.get_default_kwargs(
            user_data=None, networks=[pr_net_1['id']])
        instance = self._spawn_vm(create_kwargs)
        instance['private_ip'] = instance[
            'addresses'][pr_net_1['name']][0]['addr']
        instance['private_mac'] = instance['addresses'][
            pr_net_1['name']][0]['OS-EXT-IPS-MAC:mac_addr']
        instance['private_ip_netmask'] = pr_snet_1['cidr'].split('/')[1]
        instance['private_gateway'] = pr_snet_1['gateway_ip']
        self.instances.append(instance)

        create_kwargs = self.get_default_kwargs(
            user_data=None, networks=[pr_net_1['id'], pr_net_2['id']])
        instance = self._spawn_vm(create_kwargs)
        instance['private_ip_1'] = instance[
            'addresses'][pr_net_1['name']][0]['addr']
        instance['private_mac_1'] = instance['addresses'][
            pr_net_1['name']][0]['OS-EXT-IPS-MAC:mac_addr']
        instance['private_ip_2'] = instance[
            'addresses'][pr_net_2['name']][0]['addr']
        instance['private_mac_2'] = instance['addresses'][
            pr_net_2['name']][0]['OS-EXT-IPS-MAC:mac_addr']
        self.instances.append(instance)

        create_kwargs = self.get_default_kwargs(
            user_data=None, networks=[pr_net_2['id']])
        instance = self._spawn_vm(create_kwargs)
        instance['private_ip'] = instance[
            'addresses'][pr_net_2['name']][0]['addr']
        instance['private_mac'] = instance['addresses'][
            pr_net_2['name']][0]['OS-EXT-IPS-MAC:mac_addr']
        self.instances.append(instance)

    def spawn_copy_large_vm(self, user_datas):
        vm1_user_data, vm2_user_data = user_datas
        fixed_network_name = CONF.compute.fixed_network_name
        self.add_keypair()
        self.security_group = self._create_security_group()

        create_kwargs = self.get_default_kwargs(vm1_user_data)
        instance = self._spawn_vm(create_kwargs)
        self.instances.append(instance)

        create_kwargs = self.get_default_kwargs(vm2_user_data)
        instance = self._spawn_vm(create_kwargs)
        instance['private_ip'] = instance[
            'addresses'][fixed_network_name][0]['addr']
        self.instances.append(instance)

    def verify_ping(self, destination, interface='eth0', linux_client=None):
        if linux_client:
            linux_client.ping_host(destination, interface)
        else:
            self.linux_client.ping_host(destination)

    def check_mac(self, linux_client, expected_mac):
        linux_client.check_mac_match(expected_mac)

    def check_network_mode(self, linux_client):
        linux_client.set_promisc()
        linux_client.check_promisc()

    def wait_big_disk(self, linux_client):
        log_path = '/var/log/cloud-init-output.log'
        log_message = 'copied'
        error_message = 'Failed running'
        timeout = CONF.lis_specific.copy_large_file_timeout
        _start_time = time.time()
        while True:
            finished_script = linux_client.check_log(log_path, log_message)
            fail = linux_client.check_log(log_path, error_message)
            self.assertFalse(fail, 'Failed to run cloud-init script on vm')
            if finished_script:
                break
            if self._is_timed_out(_start_time, timeout):
                host = linux_client.ssh_client.host
                LOG.exception("Failed to retrieve cloud-init status"
                              " connection to %s@%s after %d seconds",
                              self.ssh_user, host, timeout)
                raise exceptions.SSHTimeout(host=host, user=self.ssh_user)
            time.sleep(30)

    def _is_timed_out(self, start_time, timeout):
        return (time.time() - timeout) > start_time

    def create_port_from_network(self, network):
        port = self._create_port(network)
        ip = port['fixed_ips'][0]['ip_address']
        return ip

    def set_legacy(self, linux_client):
        network = self.get_default_network()
        port = self._create_port(network)
        snet_id = port['fixed_ips'][0]['subnet_id']
        snet = self.get_subnet(snet_id)
        ip = port['fixed_ips'][0]['ip_address']
        gateway = snet['gateway_ip']
        netmask = snet['cidr'].split('/')[1]
        linux_client.set_legacy_adapter(ip, netmask, gateway)

    def _init_client(self, server_or_ip, username, private_key):
        try:
            return self.get_remote_client(
                server_or_ip=server_or_ip,
                username=username,
                private_key=private_key)
        except Exception as exc:
            LOG.exception(exc)
            self._log_console_output()
            raise exc

    def get_gateway(self):
        net = self.get_default_network()
        netw = self._list_networks(id=net['id'])
        subnet = self._list_subnets(id=netw[0]['subnets'][0])
        subnet_gateway = subnet[0]['gateway_ip']
        return subnet_gateway

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_copy_large_file(self):
        user_datas = ('big_file', 'ssh')
        self.spawn_copy_large_vm(user_datas)
        vm1 = self.instances[0]
        vm2 = self.instances[1]
        key = self.keypair['private_key']
        key_name = self.keypair['name']
        user = self.ssh_user
        vm1_client = self._init_client(vm1['floating_ip'], user, key)
        self.wait_big_disk(vm1_client)
        self.copy_large_file(vm1_client, key_name, user, vm2['floating_ip'])

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_bridge_network(self):
        self.spawn_vm_bridge()
        vm1 = self.instances[0]
        vm2 = self.instances[1]
        vm3 = self.instances[2]
        private_netmask = vm1['private_ip_netmask']
        gateway = vm1['private_gateway']
        key = self.keypair['private_key']
        user = self.ssh_user

        self.stop_vm(vm2['id'])
        self._initiate_host_client(vm2['host_name'])
        self.set_mac_spoofing(vm2)
        self.start_vm(vm2['id'])
        vm1_client = self._init_client(vm1['floating_ip'], user, key)
        vm2_client = self._init_client(vm2['floating_ip'], user, key)
        vm3_client = self._init_client(vm3['floating_ip'], user, key)

        vm1_eth1 = vm1_client.get_dev_by_mac(vm1['private_mac'])
        vm2_eth1 = vm2_client.get_dev_by_mac(vm2['private_mac_1'])
        vm2_eth2 = vm2_client.get_dev_by_mac(vm2['private_mac_2'])
        vm3_eth1 = vm3_client.get_dev_by_mac(vm3['private_mac'])

        vm1_client.set_ip(vm1['private_ip'], private_netmask, vm1_eth1)
        vm2_client.set_ip(vm2['private_ip_1'], private_netmask, vm2_eth1)
        vm2_client.set_ip(vm2['private_ip_2'], private_netmask, vm2_eth2)
        vm3_client.set_ip(vm3['private_ip'], private_netmask, vm3_eth1)

        ip = self.create_port_from_network(self.bridge_network)
        self._set_bridge(vm2_client, ip, private_netmask, vm2_eth1, vm2_eth2)
        self.verify_ping(vm3['private_ip'], vm1_eth1, vm1_client)
        self.verify_ping(vm1['private_ip'], vm3_eth1, vm3_client)

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_external_network(self):
        vm = self.spawn_vm_basic()
        key = self.keypair['private_key']
        self.linux_client = self._init_client(
            vm['floating_ip'], self.ssh_user, key)
        gateway_ip = self.get_gateway()
        self.verify_ping(gateway_ip)

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_private_network(self):
        self.spawn_vm_private()
        vm1 = self.instances[0]
        vm2 = self.instances[1]
        key = self.keypair['private_key']
        private_netmask = vm1['private_ip_netmask']

        vm1_client = self._init_client(vm1['floating_ip'], self.ssh_user, key)
        vm2_client = self._init_client(vm2['floating_ip'], self.ssh_user, key)
        vm1_eth1 = vm1_client.get_dev_by_mac(vm1['private_mac'])
        vm2_eth1 = vm2_client.get_dev_by_mac(vm2['private_mac'])
        vm1_client.set_ip(vm1['private_ip'], private_netmask, vm1_eth1)
        vm2_client.set_ip(vm2['private_ip'], private_netmask, vm2_eth1)

        self.verify_ping(vm1['private_ip'], vm1_eth1, vm2_client)

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_multiple_networks(self):
        vm = self.spawn_vm_multi_nic()
        key = self.keypair['private_key']
        linux_client = self._init_client(vm['floating_ip'], self.ssh_user, key)
        vm_eth0 = linux_client.get_dev_by_mac(vm['mac_1'])
        vm_eth1 = linux_client.get_dev_by_mac(vm['mac_2'])
        gateway_ip = self.get_gateway()
        self.verify_ping(gateway_ip, vm_eth0, linux_client)
        linux_client.refresh_iface(vm_eth1)
        self.verify_ping(vm['gateway_2'], vm_eth1, linux_client)

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_network_legacy(self):
        vm = self.spawn_vm_basic()
        key = self.keypair['private_key']
        linux_client = self._init_client(vm['floating_ip'], self.ssh_user, key)
        self._initiate_host_client(vm['host_name'])
        self.stop_vm(vm['id'])
        self.add_legacy_nic(vm['instance_name'], vm['host_name'])
        self.start_vm(vm['id'])
        linux_client.validate_authentication()
        self.set_legacy(linux_client)

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_static_mac(self):
        vm = self.spawn_vm_basic(mac=True)
        key = self.keypair['private_key']
        linux_client = self._init_client(vm['floating_ip'], self.ssh_user, key)
        self.check_mac(linux_client, vm['static_mac'])

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_network_mode(self):
        vm = self.spawn_vm_basic(mac=True)
        key = self.keypair['private_key']
        linux_client = self._init_client(vm['floating_ip'], self.ssh_user, key)
        self.check_network_mode(linux_client)

    @test.attr(type=['smoke', 'core'])
    @test.services('compute', 'network')
    def test_operstate(self):
        vm = self.spawn_vm_basic(mac=True)
        key = self.keypair['private_key']
        linux_client = self._init_client(vm['floating_ip'], self.ssh_user, key)
        self._initiate_host_client(vm['host_name'])
        self.stop_vm(vm['id'])
        self.add_empty_nic(vm['instance_name'], vm['host_name'])
        self.start_vm(vm['id'])
        self.linux_client.validate_authentication()
        self.check_operstate(linux_client)
