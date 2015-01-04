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

sudo mount /dev/sdb1 /mnt
if [ "$?" = "0" ]; then
        sudo mkdir -p /mnt/ica
        sudo dd if=/dev/sda1 of=/mnt/ica/test.dat count=2048 > /dev/null 2>&1
        if [ "$?" = "0" ]; then
            sudo umount /mnt
            if [ "$?" != "0" ]; then
                exit 55
            fi
        else
            exit 60
        fi
else
    exit 80
fi

exit 0
