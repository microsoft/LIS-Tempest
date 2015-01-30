#!/bin/bash

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

echoerr() { echo "$@" 1>&2; }

state=`sudo cat /sys/class/net/eth1/operstate`
sudo grep "down" /sys/class/net/eth1/operstate
sts=$?
    if [ 0 -ne ${sts} ]; then
        echoerr "State of eth1 $state"
        exit 1
    else
        echo "Found state down."
    fi















