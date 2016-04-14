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

########################################################################
#
# vcpu_verify_online.sh
#
# Description:
#	This script was created to automate the testing of VCPU online or offline.
#	It will verify if all the CPUs can be offline by checking the /proc/cpuinfo file.
#	The VM is configured with a number of CPU cores.
#	Each core can't be offline except vcpu0 for a successful test pass.
#
#	The test performs the following steps:
#		1. Looks for the Hyper-v timer property of each CPU under /proc/cpuinfo
#		2. Verifies if each CPU can't be offline exinclude VCPU0.
#
# Note: The Host of Hyper-V 2012 R2 don't support the CPU online or offline, so
# To make sure the CPU on guest can't be offline.
#
#########################################################################

nonCPU0inter=0

echoerr() {
        echo "$@" 1>&2;
}

#
# Getting the CPUs count
#
cpu_count=$(grep -i processor -o /proc/cpuinfo | wc -l)
echo "Info: ${cpu_count} CPU cores detected"

#
# Verifying all CPUs can't be offline except CPU0
#
for ((cpu=1 ; cpu<=$cpu_count ; cpu++)) ;do
    echo "Checking the $cpu on /sys/device/...."
    __file_path="/sys/devices/system/cpu/cpu$cpu/online"
    if [ -e "$__file_path" ]; then
		sudo bash -c "echo 0 > $__file_path > /dev/null 2>&1"
        val=`cat $__file_path`
        if [ $val -ne 0 ]; then
            echo "Info: CPU core ${cpu} can't be offline."
        else
            echoerr "Error: CPU ${cpu} can be offline!"
            exit 1
        fi
    fi
done

echo "Test pass: no CPU cores could be set to offline mode."
exit 0
