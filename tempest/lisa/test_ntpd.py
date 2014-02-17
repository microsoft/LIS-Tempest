# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack Foundation
# Copyright 2013 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
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

from tempest.api.network import common as net_common
from tempest.common import debug
from tempest.common.utils.data_utils import rand_name
from tempest import config
from tempest.openstack.common import log as logging
from tempest.common.utils.linux.remote_client import RemoteClient
from tempest.lisa import manager
from tempest.test import attr
from tempest.test import services
from tempest.common.utils.windows.remote_client import WinRemoteClient
import os

LOG = logging.getLogger(__name__)


class TestLis(manager.NetworkScenarioTest):

    """
    This smoke test suite assumes that Nova has been configured to
    boot VM's with Neutron-managed networking, and attempts to
    verify network connectivity as follows:

     * For a freshly-booted VM with an IP address ("port") on a given network:

       - the Tempest host can ping the IP address.  This implies, but
         does not guarantee (see the ssh check that follows), that the
         VM has been assigned the correct IP address and has
         connectivity to the Tempest host.

       - the Tempest host can perform key-based authentication to an
         ssh server hosted at the IP address.  This check guarantees
         that the IP address is associated with the target VM.

       # TODO(mnewby) - Need to implement the following:
       - the Tempest host can ssh into the VM via the IP address and
         successfully execute the following:

         - ping an external IP address, implying external connectivity.

         - ping an external hostname, implying that dns is correctly
           configured.

         - ping an internal IP address, implying connectivity to another
           VM on the same network.

     There are presumed to be two types of networks: tenant and
     public.  A tenant network may or may not be reachable from the
     Tempest host.  A public network is assumed to be reachable from
     the Tempest host, and it should be possible to associate a public
     ('floating') IP address with a tenant ('fixed') IP address to
     facilitate external connectivity to a potentially unroutable
     tenant IP address.

     This test suite can be configured to test network connectivity to
     a VM via a tenant network, a public network, or both.  If both
     networking types are to be evaluated, tests that need to be
     executed remotely on the VM (via ssh) will only be run against
     one of the networks (to minimize test execution time).

     Determine which types of networks to test as follows:

     * Configure tenant network checks (via the
       'tenant_networks_reachable' key) if the Tempest host should
       have direct connectivity to tenant networks.  This is likely to
       be the case if Tempest is running on the same host as a
       single-node devstack installation with IP namespaces disabled.

     * Configure checks for a public network if a public network has
       been configured prior to the test suite being run and if the
       Tempest host should have connectivity to that public network.
       Checking connectivity for a public network requires that a
       value be provided for 'public_network_id'.  A value can
       optionally be provided for 'public_router_id' if tenants will
       use a shared router to access a public network (as is likely to
       be the case when IP namespaces are not enabled).  If a value is
       not provided for 'public_router_id', a router will be created
       for each tenant and use the network identified by
       'public_network_id' as its gateway.

    """

    CONF = config.TempestConfig()

    @classmethod
    def check_preconditions(cls):
        super(TestLis, cls).check_preconditions()
        cfg = cls.config.network
        if not (cfg.tenant_networks_reachable or cfg.public_network_id):
            msg = ('Either tenant_networks_reachable must be "true", or '
                   'public_network_id must be defined.')
            cls.enabled = False
            raise cls.skipException(msg)

    @classmethod
    def setUpClass(cls):
        super(TestLis, cls).setUpClass()
        cls.check_preconditions()
        # TODO(mnewby) Consider looking up entities as needed instead
        # of storing them as collections on the class.
        cls.keypairs = {}
        cls.security_groups = {}
        cls.networks = []
        cls.subnets = []
        cls.routers = []
        cls.servers = []
        cls.floating_ips = {}

    def _get_router(self, tenant_id):
        """Retrieve a router for the given tenant id.

        If a public router has been configured, it will be returned.

        If a public router has not been configured, but a public
        network has, a tenant router will be created and returned that
        routes traffic to the public network.

        """
        router_id = self.config.network.public_router_id
        network_id = self.config.network.public_network_id
        if router_id:
            result = self.network_client.show_router(router_id)
            return net_common.AttributeDict(**result['router'])
        elif network_id:
            router = self._create_router(tenant_id)
            router.add_gateway(network_id)
            return router
        else:
            raise Exception("Neither of 'public_router_id' or "
                            "'public_network_id' has been defined.")

    def _create_router(self, tenant_id, namestart='router-smoke-'):
        name = rand_name(namestart)
        body = dict(
            router=dict(
                name=name,
                admin_state_up=True,
                tenant_id=tenant_id,
            ),
        )
        result = self.network_client.create_router(body=body)
        router = net_common.DeletableRouter(client=self.network_client,
                                            **result['router'])
        self.assertEqual(router.name, name)
        self.set_resource(name, router)
        return router

    def _create_keypairs(self):
        self.keypairs[self.tenant_id] = self.create_keypair(
            name=rand_name('keypair-smoke-'))

    def _create_security_groups(self):
        self.security_groups[self.tenant_id] = self._create_security_group()

    def _create_networks(self):
        network = self._create_network(self.tenant_id)
        router = self._get_router(self.tenant_id)
        subnet = self._create_subnet(network)
        subnet.add_to_router(router.id)
        self.networks.append(network)
        self.subnets.append(subnet)
        self.routers.append(router)

    def _check_networks(self):
        # Checks that we see the newly created network/subnet/router via
        # checking the result of list_[networks,routers,subnets]
        seen_nets = self._list_networks()
        seen_names = [n['name'] for n in seen_nets]
        seen_ids = [n['id'] for n in seen_nets]
        for mynet in self.networks:
            self.assertIn(mynet.name, seen_names)
            self.assertIn(mynet.id, seen_ids)
        seen_subnets = self._list_subnets()
        seen_net_ids = [n['network_id'] for n in seen_subnets]
        seen_subnet_ids = [n['id'] for n in seen_subnets]
        for mynet in self.networks:
            self.assertIn(mynet.id, seen_net_ids)
        for mysubnet in self.subnets:
            self.assertIn(mysubnet.id, seen_subnet_ids)
        seen_routers = self._list_routers()
        seen_router_ids = [n['id'] for n in seen_routers]
        seen_router_names = [n['name'] for n in seen_routers]
        for myrouter in self.routers:
            self.assertIn(myrouter.name, seen_router_names)
            self.assertIn(myrouter.id, seen_router_ids)

    def _create_server(self, name, network):
        tenant_id = network.tenant_id
        keypair_name = self.keypairs[tenant_id].name
        security_groups = [self.security_groups[tenant_id].name]
        create_kwargs = {
            'nics': [
                {'net-id': network.id},
            ],
            'key_name': keypair_name,
            'security_groups': security_groups,
        }
        server = self.create_server(name=name, create_kwargs=create_kwargs)
        return server

    def _create_servers(self):
        for i, network in enumerate(self.networks):

            name = rand_name('server-smoke-%d-' % i)
            server = self._create_server(name, network)
            self.servers.append(server)

    def _check_tenant_network_connectivity(self):
        if not self.config.network.tenant_networks_reachable:
            msg = 'Tenant networks not configured to be reachable.'
            LOG.info(msg)
            return
        # The target login is assumed to have been configured for
        # key-based authentication by cloud-init.
        ssh_login = self.config.compute.image_ssh_user
        private_key = self.keypairs[self.tenant_id].private_key
        for server in self.servers:
            import pdb
            pdb.set_trace()
            for net_name, ip_addresses in server.networks.iteritems():
                for ip_address in ip_addresses:
                    self._check_vm_connectivity(ip_address, ssh_login,
                                                private_key)

    def _assign_floating_ips(self):
        public_network_id = self.config.network.public_network_id
        for server in self.servers:
            floating_ip = self._create_floating_ip(server, public_network_id)
            self.floating_ips.setdefault(server, [])
            self.floating_ips[server].append(floating_ip)

    def _check_lis_presence(self):
        # The target login is assumed to have been configured for
        # key-based authentication by cloud-init.
        ssh_login = self.config.compute.image_ssh_user
        private_key = self.keypairs[self.tenant_id].private_key
        try:
            for server, floating_ips in self.floating_ips.iteritems():
                for floating_ip in floating_ips:
                    ip_address = floating_ip.floating_ip_address
                    self._test_lis(ip_address,ssh_login,private_key)
                    #self._check_vm_connectivity(ip_address,
                     #                           ssh_login,
                      #                          private_key)

        except Exception as exc:
            LOG.exception(exc)
            debug.log_ip_ns()
            raise exc
        # import pdb
        # pdb.set_trace()


    def _check_date_ntpd(self):
        # The target login is assumed to have been configured for
        # key-based authentication by cloud-init.
        ssh_login = self.config.compute.image_ssh_user
        private_key = self.keypairs[self.tenant_id].private_key
        try:
            for server, floating_ips in self.floating_ips.iteritems():
                for floating_ip in floating_ips:
                    ip_address = floating_ip.floating_ip_address
                    self._test_date(ip_address,ssh_login,private_key)
        except Exception as exc:
            LOG.exception(exc)
            debug.log_ip_ns()
            raise exc

    def _check_integrated_shutdown_services(self):

        ssh_login = self.config.compute.image_ssh_user
        private_key = self.keypairs[self.tenant_id].private_key
        try:
            for server, floating_ips in self.floating_ips.iteritems():
                for floating_ip in floating_ips:
#                    ip_address = floating_ip.floating_ip_address

                    vm_name=self.servers[0].__dict__["OS-EXT-SRV-ATTR:instance_name"]
                    host_name=self.servers[0].__dict__["OS-EXT-SRV-ATTR:hypervisor_hostname"]
                    self._test_integrated_shutdown_services(host_name,host_name, vm_name)

        except Exception as exc:
            LOG.exception(exc)
            debug.log_ip_ns()
            raise exc
    def _test_date(self, ip, username, private_key):
        linux_client = RemoteClient(ip, username, pkey=private_key)
        #output = linux_client.verify_lis_modules()
        script = 'timesync-ntp.sh'
        source = os.path.join(os.path.dirname(__file__), '..', '..', 'trollberta/bash-scripts/') + script
        destination = '/root/'

        copy_file = linux_client.copy_over(source, destination)

        output = linux_client.ssh_client.exec_command('cd /root/; dos2unix -q ' + script + ';' + ' chmod +x ' + script +';' + ' ./' + script)

        # import pdb
        # pdb.set_trace()

        self.assertNotEqual(1, output)


    def _test_lis(self, ip, username, private_key):
        linux_client = RemoteClient(ip, username, pkey=private_key)
        output = linux_client.verify_lis_modules()
        LOG.info(output)
        self.assertNotEqual(0, output)

    def _test_integrated_shutdown_services(self, host_ip, host_name, vm_name):
        username = 'Administrator'
        password = 'Passw0rd'
        cmd1 = 'powershell Get-VMIntegrationService -ComputerName ' + host_name +' -VMName '+  vm_name +' -Name Shutdown'
        print cmd1
        cmd2 = 'powershell Disable-VMIntegrationService -ComputerName ' + host_name +' -VMName '+  vm_name +' -Name Shutdown'
        cmd3 = 'powershell Enable-VMIntegrationService -ComputerName ' + host_name +' -VMName '+  vm_name +' -Name Shutdown'

        """ should work with host_name too"""

        wsmancmd = WinRemoteClient(host_ip, username, password)

        std_out, std_err, exit_code = wsmancmd.run_wsman_cmd('powershell pwd')
 #       import pdb
#        pdb.set_trace()

        LOG.debug(cmd1)
        std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd1)
        LOG.debug(std_out)
        LOG.debug(std_err)

        LOG.debug(cmd2)
        std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd2)
        LOG.debug(std_out)
        LOG.debug(std_err)

        LOG.debug(cmd1)
        std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd1)
        LOG.debug(std_out)
        LOG.debug(std_err)

        LOG.debug(cmd3)
        std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd3)
        LOG.debug(std_out)
        LOG.debug(std_err)

        LOG.debug(cmd1)
        std_out, std_err, exit_code = wsmancmd.run_wsman_cmd(cmd1)
        LOG.debug(std_out)
        LOG.debug(std_err)

        ok = "OK" in std_out

        self.assertEqual(ok, True)

    # @services('compute', 'network')
    # def test_integrated_shutdown_services(self):
    #     self._create_keypairs()
    #     self._create_security_groups()
    #     self._create_networks()
    #    # self._check_networks()
    #     self._create_servers()
    #     self._assign_floating_ips()
    #     self._check_integrated_shutdown_services()
    #     #self._check_tenant_network_connectivity()


# #    @services('compute', 'network')
#     def test_check_lis_presence(self):
#         self._create_keypairs()
#         self._create_security_groups()
#         self._create_networks()
#         #self._check_networks()
#         self._create_servers()
#         self._assign_floating_ips()
#         self._check_lis_presence()
#         #self._check_tenant_network_connectivity()

    @services('compute', 'network')
    def test_check_ntpd_date(self):
        self._create_keypairs()
        self._create_security_groups()
        self._create_networks()
        self._check_networks()
        self._create_servers()
        self._assign_floating_ips()
        self._check_date_ntpd()
        #self._check_tenant_network_connectivity()