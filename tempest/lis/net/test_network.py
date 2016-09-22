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
from tempest.common.utils.windows.remote_client import WinRemoteClient
from tempest.lis import manager
from oslo_log import log as logging
from tempest.scenario import utils as test_utils
from tempest import test
from tempest.lib import exceptions
import os
import random
import time

CONF = config.CONF

LOG = logging.getLogger(__name__)

load_tests = test_utils.load_tests_input_scenario_utils


class Network(manager.LisBase):

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
        self.image_ssh_user = CONF.validation.image_ssh_user
        self.host_username = CONF.host_credentials.host_user_name
        self.host_password = CONF.host_credentials.host_password
        if CONF.host_credentials.host_net_interface is not None:
            self.host_net_interface = '\'' +\
                                      CONF.host_credentials.host_net_interface\
                                      + '\''
        if CONF.host_credentials.host_external_sw is not None:
            self.host_external_sw = '\'' +\
                                    CONF.host_credentials.host_external_sw\
                                    + '\''
        self.scriptfolder = CONF.host_credentials.host_setupscripts_folder
        self.lis_private_network = CONF.lis.private_network

        LOG.debug('Starting test for i:{image}, f:{flavor}. '
                  'Run ssh: {ssh}, user: {ssh_user}'.format(
                      image=self.image_ref, flavor=self.flavor_ref,
                      ssh=self.run_ssh, ssh_user=self.ssh_user))

    def _initiate_wsman(self, host_name):
        try:
            self.wsmancmd = WinRemoteClient(
                host_name, self.host_username, self.host_password)

        except Exception as exc:
            LOG.exception(exc)
            raise exc

    def verify_ssh(self):
        if self.run_ssh:
            # Obtain a floating IP
            floating_network_id = CONF.network.public_network_id
            self.floating_ip = self.floating_ips_client.create_floatingip(
                floating_network_id=floating_network_id)
            self.addCleanup(self.delete_wrapper,
                            self.floating_ips_client.delete_floatingip,
                            self.floating_ip['floatingip'][
                                'floating_ip_address'])
            # Attach a floating IP
            self.compute_floating_ips_client.associate_floating_ip_to_server(
                self.floating_ip['floatingip']['floating_ip_address'],
                self.instance['id'])
            # Check ssh
            try:
                self.get_remote_client(
                    ip_address=self.floating_ip[
                        'floatingip']['floating_ip_address'],
                    username=self.image_utils.ssh_user(self.image_ref),
                    private_key=self.keypair['private_key'])
            except Exception:
                LOG.exception('ssh to server failed')
                self._log_console_output()
                raise

    def verify_external_ping(self, destination_ip):
        if self.run_ssh:
            # Obtain a floating IP
            floating_network_id = CONF.network.public_network_id
            self.floating_ip = self.floating_ips_client.create_floatingip(
                floating_network_id=floating_network_id)
            self.addCleanup(self.delete_wrapper,
                            self.floating_ips_client.delete_floatingip,
                            self.floating_ip['floatingip'][
                                'floating_ip_address'])
            # Attach a floating IP
            self.compute_floating_ips_client.associate_floating_ip_to_server(
                self.floating_ip['floatingip']['floating_ip_address'],
                self.instance['id'])
            # Check lis presence
            try:
                linux_client = self.get_remote_client(
                    ip_address=self.floating_ip[
                        'floatingip']['floating_ip_address'],
                    username=self.image_utils.ssh_user(self.image_ref),
                    private_key=self.keypair['private_key'])

                output = linux_client.verify_ping(destination_ip)
                LOG.info('Ping results ${0}'.format(output))
                self.assertNotEqual(0, output)
            except Exception:
                LOG.exception('ssh to server failed')
                self._log_console_output()
                raise

    @staticmethod
    def _remove_vswitch(host_client, sw_name=None):
        """Cleanup for vSwitch disks"""
        if sw_name is None:
            raise Exception('Please specify the switch to be removed')
        host_client.run_powershell_cmd(
            'Remove-VMSwitch -Name {sw_name} -Force '
            '-ErrorAction SilentlyContinue'.format(sw_name=sw_name))

    @staticmethod
    def _gen_random_mac():
        """
        Generate a MAC address in HyperV reserved pool.
        :return: MAC address, e.g. 00:15:5d:11:11:11
        :rtype: String
        """
        new_mac = [0x00, 0x15, 0x5d,
                   random.randint(0x00, 0xff),
                   random.randint(0x00, 0xff),
                   random.randint(0x00, 0xff)]
        return ':'.join(format(x, '02x') for x in new_mac)

    def _get_floating_ip(self):
        """
        Request create a floating IP.
        :return: floating IP
        """
        floating_network_id = CONF.network.public_network_id
        floating_ip = self.floating_ips_client.create_floatingip(
            floating_network_id=floating_network_id)
        self.addCleanup(self.delete_wrapper,
                        self.floating_ips_client.delete_floatingip,
                        floating_ip['floatingip']['floating_ip_address'])
        return floating_ip['floatingip']['floating_ip_address']

    def _create_vm(self, key_pair=None, security_groups=None, av_zone=None):
        """
        Create VM/Instance and return dict info.
        :param key_pair:
        :param security_groups:
        :param av_zone: availability_zone to force instance spawning on a host
        :return: created server dict
        :rtype: Dict
        """
        if not key_pair:
            key_pair = self.create_keypair()
        if not security_groups:
            security_group = self._create_security_group()
            security_groups = [{'name': security_group['name']}]
        kw_args = dict()
        if av_zone is not None:
            kw_args['availability_zone'] = av_zone
        instance = self.create_server(flavor=self.flavor_ref,
                                      image_id=self.image_ref,
                                      key_name=key_pair['name'],
                                      security_groups=security_groups,
                                      wait_until='ACTIVE', **kw_args)
        # Obtain a floating IP
        floating_ip = self._get_floating_ip()
        # Attach a floating IP
        self.compute_floating_ips_client.associate_floating_ip_to_server(
            floating_ip, instance['id'])
        instance['floating_ip'] = floating_ip
        return instance

    def _add_nic_to_vm(self, instance, switch_name, host_client,
                       static_mac=True, is_legacy=False, vlan=None):
        """
        Add a new network adapter to the VM with specific parameters.
        :param instance:
        :param switch_name:
        :param host_client:
        :param static_mac: Bool - generate static random mac; True by default
        :param is_legacy: Bool - create a legacy nic when True
        :param vlan: specify the vlan tag
        :return: MAC address or None if it is dynamic setup
        :rtype: Dict e.g. ps_args['VMName'],
                          ps_args['VSwitchName'],
                          ps_args['NICName'],
                          ps_args['MAC'],
                          ps_args['IsLegacy'],
                          ps_args['VLAN']
        """
        naming_suffix = str(time.time())
        self.stop_vm(instance['id'])
        ps_args = dict()
        ps_args['VMName'] = instance["OS-EXT-SRV-ATTR:instance_name"]
        ps_args['VSwitchName'] = switch_name
        ps_args['NICName'] = 'nic' + naming_suffix
        if static_mac is True:
            ps_args['MAC'] = self._gen_random_mac()
        if is_legacy is True:
            ps_args['IsLegacy'] = is_legacy
        if vlan is not None:
            ps_args['VLAN'] = vlan

        add_nic = '{}{}'.format(self.script_folder,
                                'setupscripts\\add_nic_to_VM.ps1')
        host_client.run_powershell_cmd(add_nic, **ps_args)
        self.start_vm(instance['id'])
        return ps_args

    def _set_vm_ip(self, instance, key_pair, mac, ip=None, net_mask=None):
        """
        Set VM/Instance IP using remote script SetStaticIp.sh when the 'ip' and
        'net_mask' are provided, otherwise grab using dhcp.
        :param instance:
        :param key_pair:
        :param mac:
        :param ip:
        :param net_mask:
        :return: linux_client, new_nic_name
        :rtype: Tuple
        """
        instance_ip = instance['floating_ip']
        linux_client = self.get_remote_client(
            ip_address=instance_ip,
            username=self.image_ssh_user,
            private_key=key_pair['private_key']
        )
        nic_name = linux_client.get_nic_name_by_mac(mac)
        if ip and net_mask:
            script_name = 'SetStaticIp.sh'
            script_path = '/scripts/' + script_name
            destination = '/tmp/'
            my_path = os.path.abspath(
                os.path.normpath(os.path.dirname(__file__)))
            full_script_path = my_path + script_path
            cmd_params = [ip, net_mask, nic_name]
            linux_client.execute_script(script_name, cmd_params,
                                        full_script_path, destination)
        else:
            # assuming IP can be assigned by DHCP
            linux_client.exec_command('sudo dhclient {}'.format(nic_name))
        return linux_client, nic_name

    def _create_vswitch(self, host_name, internal_sw=False,
                        private_sw=False, external_sw=False, vlan=None):
        """
        Create a new specific vSwitch on the HyperV.
        :param host_name:
        :param internal_sw:
        :param private_sw:
        :param external_sw:
        :param vlan: used to set external and internal networks vlan
        :return: host_client, switch_names dict
                or None if no switch type is specified
        :rtype: tuple
        """
        host_client = WinRemoteClient(host_name, self.host_username,
                                      self.host_password)

        naming_sf = str(time.time())
        ps_args = dict()
        if vlan is not None:
            ps_args['VLAN'] = vlan
        if internal_sw is True:
            ps_args['internalSwitch'] = 'tempest_internal' + naming_sf
        if private_sw is True:
            ps_args['privateSwitch'] = 'tempest_private' + naming_sf
        if external_sw is True:
            ps_args['externalSwitch'] = 'tempest_external' + naming_sf
            ps_args['netInterface'] = self.host_net_interface

        if ps_args:
            add_vswitch = '{}{}'.format(self.script_folder,
                                        'setupscripts\\create_vswitch.ps1')
            host_client.run_powershell_cmd(add_vswitch, **ps_args)
        else:
            raise Exception('No valid arguments found. Please specify the '
                            'switch type to be created')
        for key in ps_args:
            if 'Switch' in key and ps_args[key]:
                # adding cleanup last to avoid interference with other methods
                self._cleanups.insert(0, (self._remove_vswitch, (host_client,),
                                          {'sw_name': ps_args[key]}))
        return host_client, ps_args

    def _config_hyperv_nic(self, host_client, sw_name, ip, net_prefix):
        """
        Config static IP on the Hyper-V virtual network interface created as a
        result of the virtual switch.
        :param host_client:
        :param sw_name:
        :param ip:
        :param net_prefix:
        :return: None
        """
        config_hyperv_sw_int_ip = '{}{}'.format(
            self.script_folder, 'setupscripts\\config_host_nic.ps1')
        host_client.run_powershell_cmd(
            config_hyperv_sw_int_ip,
            Name='\'vEthernet (' + sw_name + ')\'',
            IP=ip,
            Prefix=net_prefix)

    @staticmethod
    def _config_hyperv_vm_vlan_tagging(host_client, instance, nic_name,
                                       vlan_list, base_vlan):
        """
        Configure Hyper-V VM Network adapter Vlan.
        :param host_client:
        :param instance:
        :param nic_name:
        :param vlan_list:
        :param base_vlan:
        :return: None
        """
        host_client.run_powershell_cmd(
            'Set-VMNetworkAdapterVlan -VMName {vm_name} '
            '-VMNetworkAdapterName {nic_name} '
            '-Trunk -AllowedVlanIdList {vlan_list} -NativeVlanId {base_vlan}'.
            format(vm_name=instance["OS-EXT-SRV-ATTR:instance_name"],
                   nic_name=nic_name, vlan_list=vlan_list, base_vlan=base_vlan)
        )

    def external_network_setup(self, vlan=None, create_sw=False):
        """
        Internal network setup with 2 dhcp IP instances and vSwitch creation
        attaching the tempest.conf Hyper-V interface (assuming this has an IP)
        @CONF.host_credentials.host_net_interface.
        :param: vlan: specify vlan tag for instances
        :return: Dict with:
            external_setup['instances'] = [inst1, inst2]
            external_setup['linux_clients'] = [linux_client1, linux_client2]
            external_setup['new_nics'] = [inst1_new_nic_name,
                                          inst2_new_nic_name]
            external_setup['hyperv_nics'] = [inst1_nic_args['NICName'],
                                             inst2_nic_args['NICName']]
            external_setup['new_macs'] = [inst1_nic_args['MAC'],
                                          inst2_nic_args['MAC']]
            external_setup['float_ips'] = [ip1, ip2]
            external_setup['key_pair'] = key_pair
            external_setup['host_client'] = host_client
            external_setup['host_name'] = host_name
        """
        # use existing external network assigning nova floating ips
        key_pair = self.create_keypair()
        security_group = self._create_security_group()
        security_groups = [{'name': security_group['name']}]
        inst1 = self._create_vm(key_pair=key_pair,
                                security_groups=security_groups)
        host_name = inst1["OS-EXT-SRV-ATTR:hypervisor_hostname"]
        host_zone = inst1['OS-EXT-AZ:availability_zone']
        av_zone = host_zone + ':' + host_name
        inst2 = self._create_vm(key_pair=key_pair,
                                security_groups=security_groups,
                                av_zone=av_zone)

        if create_sw is True:
            host_client, sw_names = self._create_vswitch(host_name,
                                                         external_sw=True,
                                                         vlan=vlan)
        else:
            host_client = WinRemoteClient(host_name, self.host_username,
                                          self.host_password)
            sw_names = dict()
            sw_names['externalSwitch'] = self.host_external_sw

        # Obtain a floating IPs and assign manually to new NIC
        ip1 = self._get_floating_ip()
        ip2 = self._get_floating_ip()
        net_mask = '24'
        inst1_nic_args = self._add_nic_to_vm(inst1, sw_names['externalSwitch'],
                                             host_client, vlan=vlan)
        linux_client1, inst1_new_nic_name = self._set_vm_ip(
            inst1, key_pair, inst1_nic_args['MAC'], ip1, net_mask)

        inst2_nic_args = self._add_nic_to_vm(inst2, sw_names['externalSwitch'],
                                             host_client, vlan=vlan)
        linux_client2, inst2_new_nic_name = self._set_vm_ip(
            inst2, key_pair, inst2_nic_args['MAC'], ip2, net_mask)

        external_setup = dict()
        external_setup['instances'] = [inst1, inst2]
        external_setup['linux_clients'] = [linux_client1, linux_client2]
        external_setup['new_nics'] = [inst1_new_nic_name, inst2_new_nic_name]
        external_setup['hyperv_nics'] = [inst1_nic_args['NICName'],
                                         inst2_nic_args['NICName']]
        external_setup['new_macs'] = [inst1_nic_args['MAC'],
                                      inst2_nic_args['MAC']]
        external_setup['float_ips'] = [ip1, ip2]
        external_setup['key_pair'] = key_pair
        external_setup['host_client'] = host_client
        external_setup['host_name'] = host_name

        if not all(ip for ip in external_setup['float_ips']):
            raise Exception('No IP found. Please check network availability.')

        return external_setup

    def internal_network_setup(self, vlan=None):
        """
        Internal network setup with 2 static IP instances and static IP vSwitch
        creation.
        :param: vlan: specify vlan tag for instances, can be la 2 element list
                      when checking different vlans
        :return: Dict with:
            internal_setup['instances'] = [inst1, inst2]
            internal_setup['linux_clients'] = [linux_client1, linux_client2]
            internal_setup['new_nics'] = [inst1_new_nic_name,
                                          inst2_new_nic_name]
            internal_setup['linux_ips'] = [ip1, ip2]
            internal_setup['key_pair'] = key_pair
            internal_setup['host_ip'] = host_ip
            internal_setup['host_client'] = host_client
        """
        key_pair = self.create_keypair()
        security_group = self._create_security_group()
        security_groups = [{'name': security_group['name']}]
        inst1 = self._create_vm(key_pair=key_pair,
                                security_groups=security_groups)
        host_name = inst1["OS-EXT-SRV-ATTR:hypervisor_hostname"]
        host_zone = inst1['OS-EXT-AZ:availability_zone']
        av_zone = host_zone + ':' + host_name
        inst2 = self._create_vm(key_pair=key_pair,
                                security_groups=security_groups,
                                av_zone=av_zone)

        vlan_diff = None
        if isinstance(vlan, list):
            vlan_diff = vlan[1]
            vlan = vlan[0]
        host_client, sw_names = self._create_vswitch(host_name,
                                                     internal_sw=True,
                                                     vlan=vlan)
        host_ip = '22.22.22.1'
        net_mask = '24'
        self._config_hyperv_nic(host_client, sw_names['internalSwitch'],
                                host_ip, net_mask)

        ip1 = '22.22.22.2'
        inst1_nic_args = self._add_nic_to_vm(inst1, sw_names['internalSwitch'],
                                             host_client, vlan=vlan)
        linux_client1, inst1_new_nic_name = self._set_vm_ip(
            inst1, key_pair, inst1_nic_args['MAC'], ip1, net_mask)
        ip2 = '22.22.22.3'
        if vlan_diff is not None:
            vlan = vlan_diff
        inst2_nic_args = self._add_nic_to_vm(inst2, sw_names['internalSwitch'],
                                             host_client, vlan=vlan)
        linux_client2, inst2_new_nic_name = self._set_vm_ip(
            inst2, key_pair, inst2_nic_args['MAC'], ip2, net_mask)
        internal_setup = dict()
        internal_setup['instances'] = [inst1, inst2]
        internal_setup['linux_clients'] = [linux_client1, linux_client2]
        internal_setup['new_nics'] = [inst1_new_nic_name, inst2_new_nic_name]
        internal_setup['linux_ips'] = [ip1, ip2]
        internal_setup['key_pair'] = key_pair
        internal_setup['host_ip'] = host_ip
        internal_setup['host_client'] = host_client

        return internal_setup

    def private_network_setup(self):
        """
        Private network setup with 2 static IP instances and vSwitch creation.
        :return: Dict with:
            private_setup['instances'] = [inst1, inst2]
            private_setup['linux_clients'] = [linux_client1, linux_client2]
            private_setup['new_nics'] = [inst1_new_nic_name, inst2_new_nic_name]
            private_setup['linux_ips'] = [ip1, ip2]
            private_setup['key_pair'] = key_pair
        """
        key_pair = self.create_keypair()
        security_group = self._create_security_group()
        security_groups = [{'name': security_group['name']}]
        inst1 = self._create_vm(key_pair=key_pair,
                                security_groups=security_groups)
        host_name = inst1["OS-EXT-SRV-ATTR:hypervisor_hostname"]
        host_zone = inst1['OS-EXT-AZ:availability_zone']
        av_zone = host_zone + ':' + host_name
        inst2 = self._create_vm(key_pair=key_pair,
                                security_groups=security_groups,
                                av_zone=av_zone)

        host_client, sw_names = self._create_vswitch(host_name, private_sw=True)

        ip1 = '22.22.22.2'
        net_mask = '24'
        inst1_nic_args = self._add_nic_to_vm(inst1, sw_names['privateSwitch'],
                                             host_client)
        linux_client1, inst1_new_nic_name = self._set_vm_ip(
            inst1, key_pair, inst1_nic_args['MAC'], ip1, net_mask)
        ip2 = '22.22.22.3'
        inst2_nic_args = self._add_nic_to_vm(inst2, sw_names['privateSwitch'],
                                             host_client)
        linux_client2, inst2_new_nic_name = self._set_vm_ip(
            inst2, key_pair, inst2_nic_args['MAC'], ip2, net_mask)
        private_setup = dict()
        private_setup['instances'] = [inst1, inst2]
        private_setup['linux_clients'] = [linux_client1, linux_client2]
        private_setup['new_nics'] = [inst1_new_nic_name, inst2_new_nic_name]
        private_setup['linux_ips'] = [ip1, ip2]
        private_setup['key_pair'] = key_pair

        return private_setup

    def copy_large_file(self, linux_client, private_key, src_ip, dest_ip):
        """
        Create large file on src_ip and copy via scp to dest_ip.
        :param linux_client:
        :param private_key: setup private key used at instance creation
        :param src_ip:
        :param dest_ip:
        :return:
        """
        linux_client.exec_command(
            'echo "{}" > /home/{}/.ssh/id_rsa'.format(private_key,
                                                      self.image_ssh_user))
        linux_client.exec_command('chmod 0600 /home/{0}/.ssh/id_rsa'.format(
            self.image_ssh_user))
        destination = '/tmp/'
        large_file = linux_client.create_large_file('test_file')
        copy_cmd = 'scp -v -o BindAddress={0} ' \
                   '-o UserKnownHostsFile=/dev/null ' \
                   '-o StrictHostKeyChecking=no {1} {2}@{3}:{4}'.format(
                    src_ip, large_file, self.image_ssh_user, dest_ip,
                    destination)
        o1 = linux_client.exec_command(copy_cmd)

        LOG.info('Copy results ${0}'.format(o1))


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
        external_setup = self.external_network_setup()

        o1 = external_setup['linux_clients'][0].verify_ping(
            external_setup['float_ips'][0], dev=external_setup['new_nics'][0])
        o2 = external_setup['linux_clients'][1].verify_ping(
            external_setup['float_ips'][0], dev=external_setup['new_nics'][1])

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o2))

    @test.services('compute', 'network')
    def test_internal_network(self):
        internal_setup = self.internal_network_setup()

        o1 = internal_setup['linux_clients'][0].verify_ping(
            internal_setup['linux_ips'][1], dev=internal_setup['new_nics'][0])
        o1_hyperv = internal_setup['linux_clients'][0].verify_ping(
            internal_setup['host_ip'], dev=internal_setup['new_nics'][0])
        o2 = internal_setup['linux_clients'][1].verify_ping(
            internal_setup['linux_ips'][0], dev=internal_setup['new_nics'][1])

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o1_hyperv))
        LOG.info('Ping results ${0}'.format(o2))

    @test.services('compute', 'network')
    def test_private_network(self):
        private_setup = self.private_network_setup()

        o1 = private_setup['linux_clients'][0].verify_ping(
            private_setup['linux_ips'][1], dev=private_setup['new_nics'][0])
        o2 = private_setup['linux_clients'][1].verify_ping(
            private_setup['linux_ips'][0], dev=private_setup['new_nics'][1])

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o2))

    @test.services('compute', 'network')
    def test_copy_large_file_external_network(self):
        external_setup = self.external_network_setup()

        self.copy_large_file(external_setup['linux_clients'][0],
                             external_setup['key_pair']['private_key'],
                             external_setup['float_ips'][0],
                             external_setup['float_ips'][1])

    @test.services('compute', 'network')
    def test_copy_large_file_internal_network(self):
        internal_setup = self.internal_network_setup()

        self.copy_large_file(internal_setup['linux_clients'][0],
                             internal_setup['key_pair']['private_key'],
                             internal_setup['linux_ips'][0],
                             internal_setup['linux_ips'][1])

    @test.services('compute', 'network')
    def test_copy_large_file_private_network(self):
        private_setup = self.private_network_setup()

        self.copy_large_file(private_setup['linux_clients'][0],
                             private_setup['key_pair']['private_key'],
                             private_setup['linux_ips'][0],
                             private_setup['linux_ips'][1])

    @test.services('compute', 'network')
    def test_vlan_tagging_external_network(self):
        external_setup = self.external_network_setup(vlan=10)

        o1 = external_setup['linux_clients'][0].verify_ping(
            external_setup['float_ips'][0], dev=external_setup['new_nics'][0])
        o2 = external_setup['linux_clients'][1].verify_ping(
            external_setup['float_ips'][0], dev=external_setup['new_nics'][1])

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o2))

    @test.services('compute', 'network')
    def test_vlan_tagging_internal_network(self):
        internal_setup = self.internal_network_setup(vlan=11)

        o1 = internal_setup['linux_clients'][0].verify_ping(
            internal_setup['linux_ips'][1], dev=internal_setup['new_nics'][0])
        o2 = internal_setup['linux_clients'][1].verify_ping(
            internal_setup['linux_ips'][0], dev=internal_setup['new_nics'][1])

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o2))

    @test.services('compute', 'network')
    def test_vlan_tagging_negative_internal_network(self):
        """
        Vlan tag tests (negative) for different vlans.
        :return:
        """
        internal_setup = self.internal_network_setup(vlan=[10, 11])
        try:
            o1 = internal_setup['linux_clients'][0].verify_ping(
                internal_setup['linux_ips'][1],
                dev=internal_setup['new_nics'][0])
            LOG.info('Ping results ${0}'.format(o1))
            if o1:
                raise Exception('Ping on different vlan worked. Check logs.')
        except Exception as e:
            LOG.info('Ping results exception ${0}'.format(e))
            pass
        try:
            o2 = internal_setup['linux_clients'][1].verify_ping(
                internal_setup['linux_ips'][0],
                dev=internal_setup['new_nics'][1])
            LOG.info('Ping results ${0}'.format(o2))
            if o2:
                raise Exception('Ping on different vlan worked. Check logs.')
        except Exception as e:
            LOG.info('Ping results exception ${0}'.format(e))
            pass

    @test.services('compute', 'network')
    def test_promiscuous_internal_network(self):
        internal_setup = self.internal_network_setup()

        internal_setup['linux_clients'][0].set_nic_promiscuous(
            internal_setup['new_nics'][0])
        o1 = internal_setup['linux_clients'][0].verify_ping(
            internal_setup['linux_ips'][1],
            dev=internal_setup['new_nics'][0])
        LOG.info('Ping results exception ${0}'.format(o1))
        internal_setup['linux_clients'][1].set_nic_promiscuous(
            internal_setup['new_nics'][1])
        o2 = internal_setup['linux_clients'][1].verify_ping(
            internal_setup['linux_ips'][0],
            dev=internal_setup['new_nics'][1])
        LOG.info('Ping results ${0}'.format(o2))

    @test.services('compute', 'network')
    def test_change_network(self):
        external_setup = self.external_network_setup()

        o1 = external_setup['linux_clients'][0].verify_ping(
            external_setup['float_ips'][1], dev=external_setup['new_nics'][0])
        o2 = external_setup['linux_clients'][1].verify_ping(
            external_setup['float_ips'][0], dev=external_setup['new_nics'][1])

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o2))

        _, sw_names = self._create_vswitch(external_setup['host_name'],
                                           internal_sw=True,
                                           private_sw=True)
        external_setup['host_client'].run_powershell_cmd(
            'Connect-VMNetworkAdapter -VMName {instance} -Name {nic_name} '
            '-SwitchName {sw_name}'.
            format(instance=external_setup['instances'][0][
                "OS-EXT-SRV-ATTR:instance_name"],
                   nic_name=external_setup['new_nics'][0],
                   sw_name=sw_names['internalSwitch']))
        external_setup['host_client'].run_powershell_cmd(
            'Connect-VMNetworkAdapter -VMName {instance} -Name {nic_name} '
            '-SwitchName {sw_name}'.
            format(instance=external_setup['instances'][1][
                "OS-EXT-SRV-ATTR:instance_name"],
                   nic_name=external_setup['new_nics'][1],
                   sw_name=sw_names['internalSwitch']))
        host_ip = '22.22.22.1'
        net_mask = '24'
        self._config_hyperv_nic(external_setup['host_client'],
                                sw_names['internalSwitch'],
                                host_ip, net_mask)

        ip1 = '22.22.22.2'
        self._set_vm_ip(external_setup['instances'][0],
                        external_setup['key_pair'],
                        external_setup['new_macs'][0], ip1, net_mask)
        ip2 = '22.22.22.3'
        self._set_vm_ip(external_setup['instances'][1],
                        external_setup['key_pair'],
                        external_setup['new_macs'][1], ip2, net_mask)

        o1 = external_setup['linux_clients'][0].verify_ping(
            ip2, dev=external_setup['new_nics'][0])
        o2 = external_setup['linux_clients'][1].verify_ping(
            ip1, dev=external_setup['new_nics'][1])

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o2))

        external_setup['host_client'].run_powershell_cmd(
            'Connect-VMNetworkAdapter -VMName {instance} -Name {nic_name} '
            '-SwitchName {sw_name}'.
            format(instance=external_setup['instances'][0][
                "OS-EXT-SRV-ATTR:instance_name"],
                   nic_name=external_setup['new_nics'][0],
                   sw_name=sw_names['privateSwitch']))
        external_setup['host_client'].run_powershell_cmd(
            'Connect-VMNetworkAdapter -VMName {instance} -Name {nic_name} '
            '-SwitchName {sw_name}'.
            format(instance=external_setup['instances'][1][
                "OS-EXT-SRV-ATTR:instance_name"],
                   nic_name=external_setup['new_nics'][1],
                   sw_name=sw_names['privateSwitch']))

        ip3 = '32.22.22.2'
        self._set_vm_ip(external_setup['instances'][0],
                        external_setup['key_pair'],
                        external_setup['new_macs'][0], ip3, net_mask)
        ip4 = '32.22.22.3'
        self._set_vm_ip(external_setup['instances'][1],
                        external_setup['key_pair'],
                        external_setup['new_macs'][1], ip4, net_mask)

        o1 = external_setup['linux_clients'][0].verify_ping(
            ip4, dev=external_setup['new_nics'][0])
        o2 = external_setup['linux_clients'][1].verify_ping(
            ip3, dev=external_setup['new_nics'][1])

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o2))

    @test.services('compute', 'network')
    def test_jumbo_frames_external_network(self):
        external_setup = self.external_network_setup()
        mtu = 65521
        external_setup['linux_clients'][0].set_nic_mtu_size(
            external_setup['new_nics'][0], mtu)
        external_setup['linux_clients'][1].set_nic_mtu_size(
            external_setup['new_nics'][1], mtu)

        # for ping packet size should be -28 to allow packet padding
        o1 = external_setup['linux_clients'][0].verify_ping(
            external_setup['float_ips'][1], dev=external_setup['new_nics'][0],
            mtu_size=mtu - 28)
        o2 = external_setup['linux_clients'][1].verify_ping(
            external_setup['float_ips'][0], dev=external_setup['new_nics'][1],
            mtu_size=mtu - 28)

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o2))

    @test.services('compute', 'network')
    def test_jumbo_frames_internal_network(self):
        internal_setup = self.internal_network_setup()
        mtu = 65521
        internal_setup['linux_clients'][0].set_nic_mtu_size(
            internal_setup['new_nics'][0], mtu)
        internal_setup['linux_clients'][1].set_nic_mtu_size(
            internal_setup['new_nics'][1], mtu)

        # for ping packet size should be -28 to allow packet padding
        o1 = internal_setup['linux_clients'][0].verify_ping(
            internal_setup['linux_ips'][1], dev=internal_setup['new_nics'][0],
            mtu_size=mtu - 28)
        o2 = internal_setup['linux_clients'][1].verify_ping(
            internal_setup['linux_ips'][0], dev=internal_setup['new_nics'][1],
            mtu_size=mtu - 28)

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o2))

    @test.services('compute', 'network')
    def test_legacy_nic_internal_network(self):
        key_pair = self.create_keypair()
        security_group = self._create_security_group()
        security_groups = [{'name': security_group['name']}]
        instance = self._create_vm(key_pair=key_pair,
                                   security_groups=security_groups)

        host_name = instance["OS-EXT-SRV-ATTR:hypervisor_hostname"]
        host_client, sw_names = self._create_vswitch(host_name,
                                                     internal_sw=True)
        host_ip = '22.22.22.1'
        net_mask = '24'
        self._config_hyperv_nic(host_client, sw_names['internalSwitch'],
                                host_ip, net_mask)

        inst1_nic_args = self._add_nic_to_vm(instance,
                                             sw_names['internalSwitch'],
                                             host_client)
        inst2_nic_args = self._add_nic_to_vm(instance,
                                             sw_names['internalSwitch'],
                                             host_client, is_legacy=True)

        ip1 = '22.22.22.2'
        ip2 = '22.22.22.3'
        # Note: prep instance to preserve net adapter boot order, otherwise the
        # eth order will mismatch and loose connectivity
        linux_client, instance_nic_name1 = self._set_vm_ip(
            instance, key_pair, inst1_nic_args['MAC'], ip1, net_mask)
        _, instance_nic_name2 = self._set_vm_ip(
            instance, key_pair, inst2_nic_args['MAC'], ip2, net_mask)

        # ensure legacy net is supported by setting a single cpu online
        linux_client.set_cpu_count_online(1)

        o1 = linux_client.verify_ping(host_ip, dev=instance_nic_name1)
        o2 = linux_client.verify_ping(host_ip, dev=instance_nic_name2)

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o2))

    @test.services('compute', 'network')
    def test_vlan_trunk_external_network(self):
        external_setup = self.external_network_setup()
        # execute core for trunk mode vlan
        trunk_vlan = 99
        try:
            o = external_setup['linux_clients'][0].exec_command(
                'modprobe --first-time 8021q')
            LOG.info(o)
        except exceptions.SSHExecCommandFailed as e:
            if "Module already in kernel" in e:
                pass
        external_setup['linux_clients'][0].create_nic_vlan_tag(
            nic_name=external_setup['new_nics'][0], vlan=trunk_vlan)
        ip1 = '172.27.1.1'
        brd = '172.27.1.255'
        net_mask = '24'
        vlan_nic1 = '{nic_name}.{vlan_id}'.format(
            nic_name=external_setup['new_nics'][0], vlan_id=trunk_vlan)
        external_setup['linux_clients'][0].assign_static_ip(vlan_nic1, ip1,
                                                            net_mask, brd=brd)
        external_setup['linux_clients'][0].set_nic_state(vlan_nic1)
        LOG.info(external_setup['linux_clients'][0].exec_command(
            'ifconfig'))
        try:
            o = external_setup['linux_clients'][1].exec_command(
                'modprobe --first-time 8021q')
            LOG.info(o)
        except Exception as e:
            if "Module already in kernel" in e:
                pass
        external_setup['linux_clients'][1].create_nic_vlan_tag(
            nic_name=external_setup['new_nics'][1], vlan=trunk_vlan)
        vlan_nic2 = '{nic_name}.{vlan_id}'.format(
            nic_name=external_setup['new_nics'][1], vlan_id=trunk_vlan)
        ip2 = '172.27.1.2'
        external_setup['linux_clients'][1].assign_static_ip(vlan_nic2, ip2,
                                                            net_mask, brd=brd)
        external_setup['linux_clients'][1].set_nic_state(vlan_nic1)
        LOG.info(external_setup['linux_clients'][1].exec_command(
            'ifconfig'))

        self._config_hyperv_vm_vlan_tagging(external_setup['host_client'],
                                            external_setup['instances'][0],
                                            external_setup['hyperv_nics'][0],
                                            '1-100', 10)
        self._config_hyperv_vm_vlan_tagging(external_setup['host_client'],
                                            external_setup['instances'][1],
                                            external_setup['hyperv_nics'][1],
                                            '1-100', 10)

        o1 = external_setup['linux_clients'][0].verify_ping(ip1, dev=vlan_nic1)
        o2 = external_setup['linux_clients'][1].verify_ping(ip1, dev=vlan_nic2)

        LOG.info('Ping results ${0}'.format(o1))
        LOG.info('Ping results ${0}'.format(o2))

    def test_operstate_internal_network(self):
        """
        1.shut down a guest, change the network adapter to "Not connected" by
        Hyper-V Manager
        2.power on and log in the guest, check the network adapter link status
        by "#cat /sys/class/net/ethN/operstate"(or use #ethtool ethN|grep Link)
        """
        key_pair = self.create_keypair()
        security_group = self._create_security_group()
        security_groups = [{'name': security_group['name']}]
        instance = self._create_vm(key_pair=key_pair,
                                   security_groups=security_groups)

        host_name = instance["OS-EXT-SRV-ATTR:hypervisor_hostname"]
        host_client, sw_names = self._create_vswitch(host_name,
                                                     internal_sw=True)
        host_ip = '22.22.22.1'
        net_mask = '24'
        self._config_hyperv_nic(host_client, sw_names['internalSwitch'],
                                host_ip, net_mask)

        ip = '22.22.22.2'
        inst_nic_args = self._add_nic_to_vm(instance,
                                            sw_names['internalSwitch'],
                                            host_client)

        linux_client, instance_nic_name = self._set_vm_ip(
            instance, key_pair, inst_nic_args['MAC'], ip, net_mask)

        self.stop_vm(instance['id'])
        host_client.run_powershell_cmd(
            'Disconnect-VMNetworkAdapter -VMName {instance} -Name {nic_name}'.
            format(instance=instance["OS-EXT-SRV-ATTR:instance_name"],
                   nic_name=instance_nic_name))
        self.start_vm(instance['id'])
        operstate = linux_client.exec_command(
            'cat /sys/class/net/{nic_name}/operstate'.format(
                nic_name=instance_nic_name))
        if 'down' in operstate:
            LOG.info('Operstate is {}'.format(operstate))
        else:
            raise Exception('Could not verify operstate: {}'.format(operstate))
