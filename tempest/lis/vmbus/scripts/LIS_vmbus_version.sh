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

echoerr() {
        echo "$@" 1>&2;
}

#
# Checking for the VMBus protocol string in dmesg
#
vmbus_string=`sudo dmesg | grep "Vmbus version:" | sed 's/^\[[^]]*\] *//'`

if [ "$vmbus_string" = "" ]; then
        echoerr "Test failed! Could not find the VMBus protocol string in dmesg."
        exit 1
        elif [[ "$vmbus_string" == *hv_vmbus*Hyper-V*Host*Build*Vmbus*version:* ]]; then
                echo "Test passed! Found a matching VMBus string:\n ${vmbus_string}"
fi

exit 0
