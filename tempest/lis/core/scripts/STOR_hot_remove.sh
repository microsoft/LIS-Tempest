#!/bin/bash

########################################################################
#
# Linux on Hyper-V and Azure Test Code, ver. 1.0.0
# Copyright (c) Microsoft Corporation
#
# All rights reserved.
# Licensed under the Apache License, Version 2.0 (the ""License"");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# THIS CODE IS PROVIDED *AS IS* BASIS, WITHOUT WARRANTIES OR CONDITIONS
# OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION
# ANY IMPLIED WARRANTIES OR CONDITIONS OF TITLE, FITNESS FOR A PARTICULAR
# PURPOSE, MERCHANTABLITY OR NON-INFRINGEMENT.
#
# See the Apache Version 2.0 License for specific language governing
# permissions and limitations under the License.
#
########################################################################

expectedDiskCound=$1

### do fdisk to rescan the scsi bus
sudo fdisk -l > /dev/null
sudo fdisk -l > /dev/null
sudo fdisk -l > /dev/null
sudo fdisk -l > /dev/null

#
# Compute the number of sd* drives on the system.
#
sdCount=0
sdCount=$(sudo fdisk -l | grep "Disk /dev/sd*" | wc -l)
sdCount=$((sdCount-1))

if [ $sdCount == $expectedDiskCound ]; then
    exit 30
else
    if [ "$sdCount" != "0" ]; then
        exit 40
    fi
fi

exit 0
