# Copyright 2015 Cloudbase Solutions Srl
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

import functools
import re
from tempest import exceptions
from tempest.common.utils import classloader
from tempest.common.utils.linux import remote_client
from oslo_log import log


DEFAULT_OS_HELPER = 'tempest.common.utils.linux.remote_client.RemoteClient'

_compile = functools.partial(re.compile, flags=re.I)
FORMATS = (
    (_compile(br'(^(?!red hat 7))(^(red hat|oracle|fedora))'),
     'tempest.common.utils.linux.remote_client.FedoraUtils'),
    (_compile(br'^(opensuse|suse linux).*'),
     'tempest.common.utils.linux.remote_client.SuseUtils'),
    (_compile(br'^(debian|ubuntu).*'),
     'tempest.common.utils.linux.remote_client.DebianUtils'),
    (_compile(br'^(red hat 7)'),
     'tempest.common.utils.linux.remote_client.Fedora7Utils')
)
del _compile

LOG = log.getLogger(__name__)


def _get_os_utils(distro):
    for pattern, os_helper_class in FORMATS:
        if pattern.search(distro):
            return os_helper_class
    return DEFAULT_OS_HELPER


def get_os_utils(**kvargs):
    cl = classloader.ClassLoader()
    linux_client = remote_client.RemoteClientBase(**kvargs)
    try:
        linux_client.validate_authentication()
    except exceptions.SSHTimeout:
        LOG.exception('ssh connection failed')
        raise
    distro = linux_client.get_os_type()
    os_helper = _get_os_utils(distro)
    return cl.load_class(os_helper)(**kvargs)
