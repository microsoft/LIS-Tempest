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

# Count the Number of partition present in added new Disk .
count=0
for disk in $(sudo cat /proc/partitions | grep sd | awk '{print $4}')
do
        if [[ "$disk" != "sda"* ]];
        then
                ((count++))
        fi
done

((count--))

# Format, Partition and mount all the new disk on this system.
for driveName in /dev/sd*[^0-9];
do
    #
    # Skip /dev/sda
    #
    if [ $driveName != "/dev/sda"  ] ; then

    # Delete the exisiting partition

    for (( c=1 ; c<=count; count--))
        do
            (echo d; echo $c ; echo ; echo w) | sudo fdisk $driveName
            sleep 5
        done

# Partition Drive
    (echo n; echo p; echo 1; echo ; echo +500M; echo ; echo w) | sudo fdisk $driveName
    sleep 5
    (echo n; echo p; echo 2; echo ; echo; echo ; echo w) | sudo fdisk $driveName
    sleep 5
    sts=$?
  if [ 0 -ne ${sts} ]; then
      echo "Error:  Partitioning disk Failed ${sts}"
      exit 1
  fi

   sleep 1

# Create file sytem on it .
   echo "y" | sudo mkfs.$FILESYS ${driveName}1  ; echo "y" | sudo mkfs.$FILESYS ${driveName}2
   sts=$?
        if [ 0 -ne ${sts} ]; then
            echoerr "Error:  creating filesystem  Failed ${sts}"
            exit 1
        fi

   sleep 1

# mount the disk
   MountName="/mnt/1"
   if [ ! -e ${MountName} ]; then
     sudo mkdir $MountName
   fi
   MountName1="/mnt/2"
   if [ ! -e ${MountName1} ]; then
     sudo mkdir $MountName1
   fi
   sudo mount ${driveName}1 $MountName ; sudo mount ${driveName}2 $MountName1
   sts=$?
       if [ 0 -ne ${sts} ]; then
           echoerr "Error:  mounting disk Failed ${sts}"
           exit 1
       fi
    fi
done