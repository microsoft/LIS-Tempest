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

echoerr() { echo "$@" 1>&2; }

# Load array with names of existing interfaces
i=0
#
#for interface in $( sudo /sbin/ifconfig | grep '^[a-z]' | sed 's/ .*//' ) this for everything else, the other one for rhel
for interface in $( sudo /sbin/ifconfig | grep '^[a-z]' | sed 's/: .*//' )
do
    echo $interface
    if [ $interface != "lo" ]; then

        sudo ifconfig $interface down
        sts=$?
        if [ 0 -ne ${sts} ]; then
            echoerr "Taking interfaces down: Failed"
            exit 1
        else
            echo "Interface $interface : down"
        fi

        let i=i+1
    fi
done

for interface in $( sudo /sbin/ifconfig | grep '^[a-z]' | sed 's/ .*//' )
do
    echo $interface
    if [ $interface != "lo" ]; then

        sudo ifconfig $interface down
        sts=$?
        if [ 0 -ne ${sts} ]; then
            echoerr "Taking interfaces down: Failed"
            exit 1
        else
            echo "Interface $interface : down"
        fi

        let i=i+1
    fi
done
exit 0