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
import re
import time
import six

from tempest.common import ssh
from tempest import config
from tempest import exceptions
from tempest.openstack.common import log

CONF = config.CONF

LOG = log.getLogger(__name__)


class RemoteClientBase():

    SCRIPTS_BASE_PATH = 'tempest/lis/bash-scripts/'
    # NOTE(afazekas): It should always get an address instead of server

    def __init__(self, server, username, password=None, pkey=None):
        ssh_timeout = CONF.compute.ssh_timeout
        network = CONF.compute.network_for_ssh
        ip_version = CONF.compute.ip_version_for_ssh
        ssh_channel_timeout = CONF.compute.ssh_channel_timeout
        if isinstance(server, six.string_types):
            ip_address = server
        else:
            addresses = server['addresses'][network]
            for address in addresses:
                if address['version'] == ip_version:
                    ip_address = address['addr']
                    break
            else:
                raise exceptions.ServerUnreachable()
        self.ssh_client = ssh.Client(ip_address, username, password,
                                     ssh_timeout, pkey=pkey,
                                     channel_timeout=ssh_channel_timeout)

    def get_os_type(self):
        script_name = 'get_os.sh'
        destination = '/tmp/'

        script_path = self.SCRIPTS_BASE_PATH + script_name
        full_script_path = os.path.abspath(
            os.path.normpath(
                os.path.join(os.getcwd(), script_path)))

        cmd_params = []
        distro = self.execute_script(
            script_name, cmd_params, full_script_path, destination)
        return distro.strip().lower()

    def exec_command(self, cmd):
        return self.ssh_client.exec_command(cmd)

    def copy_over(self, source, destination):
        output = self.ssh_client.sftp(source, destination)
        return output

    def validate_authentication(self):
        """Validate ssh connection and authentication
           This method raises an Exception when the validation fails.
        """
        self.ssh_client.test_connection_auth()

    def execute_script(self, cmd, cmd_params, source, destination):
        try:
            utils_name = 'utils.sh'
            utils_path = self.SCRIPTS_BASE_PATH + utils_name
            utils_source = os.path.abspath(
                os.path.normpath(
                    os.path.join(os.getcwd(), utils_path)))
            self.copy_over(utils_source, destination)
            self.copy_over(source, destination)
            cmd_args = ' '.join(str(x) for x in cmd_params)
            command = ('cd %(dest)s; chmod +x %(cmd)s; '
                       './%(cmd)s %(cmd_args)s') % {
                'dest': destination,
                'cmd': cmd,
                'cmd_args': cmd_args}
            return self.exec_command(command)

        except exceptions.SSHExecCommandFailed as exc:
            LOG.exception(exc)
            raise exc

        except Exception as exc:
            LOG.exception(exc)
            raise exc


class RemoteClient(RemoteClientBase):

    def hostname_equals_servername(self, expected_hostname):
        # Get host name using command "hostname"
        actual_hostname = self.exec_command("hostname").rstrip()
        return expected_hostname == actual_hostname

    def get_ram_size_in_mb(self):
        output = self.exec_command('free -m | grep Mem')
        if output:
            return output.split()[1]

    def get_number_of_vcpus(self):
        command = 'cat /proc/cpuinfo | grep processor | wc -l'
        output = self.exec_command(command)
        return int(output)

    def get_partitions(self):
        # Return the contents of /proc/partitions
        command = 'cat /proc/partitions'
        output = self.exec_command(command)
        return output

    def get_boot_time(self):
        cmd = 'cut -f1 -d. /proc/uptime'
        boot_secs = self.exec_command(cmd)
        boot_time = time.time() - int(boot_secs)
        return time.localtime(boot_time)

    def write_to_console(self, message):
        message = re.sub("([$\\`])", "\\\\\\\\\\1", message)
        # usually to /dev/ttyS0
        cmd = 'sudo sh -c "echo \\"%s\\" >/dev/console"' % message
        return self.exec_command(cmd)

    def set_ip(self, ip, netmask, interface):
        cmd = ('sudo ip addr add %(ip)s/%(netmask)s dev %(interface)s;'
               'sudo ip link set %(interface)s down;'
               'sudo ip link set %(interface)s up;'
               '') % {'interface': interface,
                      'ip': ip,
                      'netmask': netmask}
        return self.exec_command(cmd)

    def refresh_iface(self, interface):
        cmd = ('sudo dhclient %(interface)s -r; '
               'sudo dhclient %(interface)s ; '
               'sudo ip link set %(interface)s down; '
               'sudo ip link set %(interface)s up') % {'interface': interface}
        return self.exec_command(cmd)

    def get_dev_by_mac(self, mac):
        # output like /sys/class/net/eth0/address:fa:16:3e:19:39:9e
        # split_by_slash
        cmd = ('device_full_path=$(sudo find /sys/class/net/*/ -name address | xargs grep "%s" );'
               'elements=(${device_full_path//// }) ; '
               ' echo ${elements[3]}') % mac
        return self.exec_command(cmd).strip()

    def set_legacy_adapter(self, ip, netmask, gateway):
        cmd = ('adapter=$(for i in `sudo ls /proc/sys/net/ipv4/conf`; do '
               ' if [ "$i" != "all" -a "$i" != "lo" -a "$i" != "eth0" -a "$i" != "default" ];then '
               ' echo $i; '
               'fi; done); '
               ' sudo ip addr add %(ip)s/%(netmask)s dev $adapter; '
               ' sudo route add default gw %(gateway)s $adapter '
               ' sudo ping -I $adapter -c1 %(gateway)s') % {'ip': ip, 'netmask': netmask, 'gateway': gateway}
        return self.exec_command(cmd)

    def check_log(self, log_path, log_message):
        cmd = (
            'sudo tail %(log)s | grep "%(msg)s" | wc -l') % {'log': log_path, 'msg': log_message}
        return int(self.exec_command(cmd))

    def ping_host(self, host, iface='eth0'):
        cmd = 'ping -I %s -c1 -w1 %s' % (iface, host)
        return self.exec_command(cmd)

    def check_mac_match(self, mac_address):
        cmd = 'sudo /sbin/ifconfig | grep %s' % mac_address
        return self.exec_command(cmd)

    def set_promisc(self):
        cmd = 'sudo ip link set dev eth0 promisc on'
        return self.exec_command(cmd)

    def check_promisc(self):
        cmd = 'sudo cat /var/log/messages | grep "promisc" '
        return self.exec_command(cmd)

    def get_mac_address(self):
        cmd = "/sbin/ifconfig | awk '/HWaddr/ {print $5}'"
        return self.exec_command(cmd)

    def get_ip_list(self):
        cmd = "/bin/ip address"
        return self.exec_command(cmd)

    def assign_static_ip(self, nic, addr):
        cmd = "sudo /bin/ip addr add {ip}/{mask} dev {nic}".format(
            ip=addr, mask=CONF.network.tenant_network_mask_bits,
            nic=nic
        )
        return self.exec_command(cmd)

    def turn_nic_on(self, nic):
        cmd = "sudo /bin/ip link set {nic} up".format(nic=nic)
        return self.exec_command(cmd)

    def get_pids(self, pr_name):
        # Get pid(s) of a process/program
        cmd = "ps -ef | grep %s | grep -v 'grep' | awk {'print $1'}" % pr_name
        return self.exec_command(cmd).split('\n')

    def verify_lis_modules(self):
        command = 'lsmod | grep hv_ | wc -l'
        output = self.exec_command(command)
        return int(output)

    def get_cpu_count(self):
        command = 'cat /proc/cpuinfo | grep processor | wc -l'
        output = self.exec_command(command)
        return int(output)

    def create_file(self, file_name):
        cmd = 'echo abc > %s' % file_name
        return self.exec_command(cmd)

    def delete_file(self, file_name):
        cmd = 'rm -f %s' % file_name
        output = self.exec_command(cmd)
        return output

    def verify_deamon(self, deamon):
        cmd = 'ps cax | grep %s' % deamon
        output = self.exec_command(cmd)
        return output

    def verify_file(self, file_name):
        cmd = 'cat %s' % file_name
        return self.exec_command(cmd)

    def check_file_existence(self, file_name):
        cmd = ' [ -f %s ] && echo 1 || echo 0' % file_name
        return int(self.exec_command(cmd))

    def get_unix_time(self):
        command = 'date +%s'
        output = self.exec_command(command)
        return int(output)

    def get_disks_count(self, sleep_count=1):
        command = 'sleep ' + \
            str(sleep_count) + '; fdisk -l | grep "Disk /dev/sd*" | wc -l'
        output = self.exec_command(command)
        return int(output)

    def verify_ping(self, destination_ip, dev='eth0'):
        cmd = "ping -I {dev} -c 10 {destination_ip}".format(
            dev=dev, destination_ip=destination_ip)
        return self.exec_command(cmd)

    def verify_vss_deamon(self):
        return self.verify_deamon('hv_vss_daemon')


class DebianUtils(RemoteClient):

    def get_os_type(self):
        return 'debian'


class FedoraUtils(RemoteClient):

    def get_os_type(self):
        return 'fedora'


class Fedora7Utils(RemoteClient):

    def get_os_type(self):
        return 'fedora7'

    def verify_deamon(self, deamon_name):
        cmd = 'sudo systemctl restart %s' % deamon_name
        output = self.exec_command(cmd)
        return output

    def verify_vss_deamon(self):
        return self.verify_deamon('hypervvssd')


class SuseUtils(RemoteClient):

    def get_os_type(self):
        return 'suse'

    def refresh_iface(self, interface):
        cmd = ('sudo dhcpcd %(interface)s -k; '
               'sudo dhcpcd %(interface)s ; '
               'sudo ip link set %(interface)s down; '
               'sudo ip link set %(interface)s up') % {'interface': interface}
        return self.exec_command(cmd)
