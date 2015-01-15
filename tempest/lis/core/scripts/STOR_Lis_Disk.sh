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

expectedDiskCount=$1
fileSystem=$2
if [[ "$fileSystem" =~ "reiserfs" ]]; then
    sudo man mkfs.reiserfs > /dev/null
    if [ "$?" != "0" ]; then
        . utils.sh
        installReiserfs
    fi
fi
if [[ "$fileSystem" =~ "btrfs" ]]; then
    sudo man mkfs.btrfs > /dev/null
    if [ "$?" != "0" ]; then
        . utils.sh
        installBtrfs
    fi
fi

echoerr() { echo "$@" 1>&2; }
sdCount=0
for drive in $(sudo find /sys/devices/ -name sd* | grep 'sd.$' | sed 's/.*\(...\)$/\1/')
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
for drive in $(sudo find /sys/devices/ -name sd* | grep 'sd.$' | sed 's/.*\(...\)$/\1/')
do
    if [ ${drive} = "sda" ];
    then
        continue
    fi
    driveName="/dev/${drive}"
    (echo d;echo;echo w) | sudo fdisk $driveName
    (echo n;echo p;echo 1;echo;echo;echo w) | sudo fdisk $driveName
    if [ "$?" != "0" ]; then
        exit 90
    fi
    sleep 5
    if [[ "$fileSystem" =~ "reiserfs" ]]; then
        sudo mkfs.$fileSystem -q ${driveName}1
        if [ "$?" != "0" ]; then
            exit 80
        fi
        sudo reiserfstune -l newpartition ${driveName}1
        if [ "$?" != "0" ]; then
            exit 80
        fi
    else
        sudo mkfs.$fileSystem ${driveName}1
    fi
    sudo mkdir /mnt/${drive}1
    sudo mount ${driveName}1 /mnt/${drive}1
    if [ "$?" != "0" ]; then
        exit 80
    fi
    sudo mkdir /mnt/${drive}1/Example
    sudo dd if=/dev/zero of=/mnt/${drive}1/Example/data bs=10M count=50
    if [ "$?" != "0" ]; then
        echoerr "Failed to dd /mnt/Example/data"
        exit 90
   fi
    sudo ls /mnt/${drive}1/Example
    if [ "$?" != "0" ]; then
        echoerr "Failed to ls /mnt/"
        exit 55
    fi
    sudo df -h
    if [ "$?" != "0" ]; then
        echoerr "Failed to df -h"
        exit 55
    fi
    sudo umount /mnt/${drive}1
    if [ "$?" != "0" ]; then
        echoerr "Failed to lumount /mnt/"
        exit 55
    fi
done
exit 0
