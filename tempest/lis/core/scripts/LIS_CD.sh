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

cd ~

# check if CDROM  module is loaded or no
CD=$(sudo lsmod | grep ata_piix)
if [[ $CD != "" ]] ; then
	echo "ata_piix module is present"
else
	echo "ata_piix module is not present in VM"
	echo "Loading ata_piix module "
	sudo insmod /lib/modules/`uname -r`/kernel/drivers/ata/ata_piix.ko
	sts=$?
    if [ 0 -ne ${sts} ]; then
        echoerr "Unable to load ata_piix module"
	    echoerr "Aborting test."
	    exit 1
    else
	    echo " ata_piix module loaded : Success"
    fi
fi


echo "##### Mount the CDROM #####"
sudo mount /dev/dvd /mnt/
sts=$?
    if [ 0 -ne ${sts} ]; then
        echoerr "Unable to mount the CDROM"
	    echoerr "Mount CDROM failed: ${sts}"
	    exit 1
    else
	    echo " CDROM detected : Success"
    fi

echo "##### Perform read  operations on the CDROM ######"
cd /mnt/

ls /mnt
sts=$?
    if [ 0 -ne ${sts} ]; then
        echoerr "Unable to read datafrom the CDROM"
	    echoerr "Read data from CDROM failed: ${sts}"
	    exit 1
    else
	    echo "Data read inside CDROM : Success"
    fi
cd ~
sudo umount /mnt/
sts=$?
    if [ 0 -ne ${sts} ]; then
        echoerr "Unable to unmount the CDROM"
	    echoerr "umount failed: ${sts}"
	    exit 1
    else
	    echo " CDROM unmount: Success"
    fi















