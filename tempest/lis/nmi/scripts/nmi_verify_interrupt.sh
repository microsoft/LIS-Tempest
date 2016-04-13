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
# nmi_verify_interrupt.sh
# Description:
#	This script was created to automate the testing of a Linux
#	Integration services. This script will verify if a NMI sent
#	from Hyper-V is received  inside the Linux VM, by checking the
#	/proc/interrupts file.
#	The test performs the following steps:
#    1. Looks for the NMI property of each CPU.
#	 2. Verifies if each CPU has received a NMI.
#
################################################################

echoerr() {
        echo "$@" 1>&2;
}

#
# Getting the CPUs NMI property count
#
cpu_count=$(grep CPU -o /proc/interrupts | wc -l)

echo "Info: ${cpu_count} CPUs found"

#
# Verifying if NMI is received by checking the /proc/interrupts file
#
while read line
do
	if [[ $line = *NMI* ]]; then
        for ((  i=0 ;  i<=$cpu_count-1;  i++ ))
        do
            nmiCount=`echo $line | cut -f $(( $i+2 )) -d ' '`
            echo "Info: CPU ${i} interrupt count = ${nmiCount}"
            if [ $nmiCount -ne 0 ]; then
                echo "Info: NMI received at CPU ${i}"
            else
                echoerr "Error: CPU {$i} did not receive a NMI!"
                exit 1
            fi
        done
    fi
done < "/proc/interrupts"

echo "Info: NMI calls are received on all CPU cores."
exit 0