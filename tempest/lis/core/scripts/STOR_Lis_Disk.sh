#!/bin/bash

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


expectedDiskCount=$1
fileSystem=$2
echoerr() { echo "$@" 1>&2; }
sdCount=0
for drive in $(find /sys/devices/ -name sd* | grep 'sd.$' | sed 's/.*\(...\)$/\1/')
do
    sdCount=$((sdCount+1))
done
sdCount=$((sdCount-1))
if [ $sdCount != $expectedDiskCount ];
then
    echoerr "Disk count inside vm is different than expectedDiskCount"
    exit 10
fi

firstDrive=1
for drive in $(find /sys/devices/ -name sd* | grep 'sd.$' | sed 's/.*\(...\)$/\1/')
do
    if [ ${drive} = "sda" ];
    then
        continue
    fi
    driveName="/dev/${drive}"
    (echo d;echo;echo w)|fdisk  $driveName
    (echo n;echo p;echo 1;echo;echo;echo w)|fdisk  $driveName
    if [ "$?" = "0" ]; then
        sleep 5
        mkfs.$fileSystem  ${driveName}1
        if [ "$?" = "0" ]; then
            mount ${driveName}1 /mnt
                    if [ "$?" = "0" ]; then
                        mkdir /mnt/Example
                        dd if=/dev/zero of=/mnt/Example/data bs=10M count=50
                        if [ "$?" = "0" ]; then
                            ls /mnt/Example
                            df -h
                            umount /mnt
                            if [ "$?" != "0" ]; then
                                exit 55
                            fi
                    else
                        exit 60
                    fi
                else
                    exit 70
                fi
            else
                exit 80
            fi
    else
        exit 90
    fi
done

exit 0
