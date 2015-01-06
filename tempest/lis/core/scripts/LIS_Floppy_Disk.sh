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


echoerr() { echo "$@" 1>&2; }


#
# check if floppy module is loaded or not
#
echo "Check if floppy module is loaded"

FLOPPY=`lsmod | grep floppy`
if [[ $FLOPPY != "" ]] ; then
    echo "Floppy disk  module is present"
else
    echo "Floppy disk module is not present in VM"
    echo "Loading Floppy disk module..."
    modprobe floppy
    sts=$?
    if [ 0 -ne ${sts} ]; then
	   echoerr "Floppy disk module loaded : Failed!"
        exit 1
    else
        echo  "Floppy disk module loaded inside the VM"
        sleep 3
    fi
fi

#
# Format the floppy disk
#
echo "mkfs -t vfat /dev/fd0"
mkfs -t vfat /dev/fd0
if [ $? -ne 0 ]; then
    msg="Unable to mkfs -t vfat /dev/fd0"
    echoerr "Error: ${msg}"
    exit 20
fi

#
# Mount the floppy disk
#
echo "Mount the floppy disk"
mount /dev/fd0 /mnt/
sts=$?
if [ 0 -ne ${sts} ]; then
	echoerr "Unable to mount the Floppy Disk"
    exit 1
else
    echo  "Floppy disk is mounted successfully inside the VM"
    echo "Floppy disk is detected inside the VM"
fi

echo "Perform read ,write and delete  operations on the Floppy Disk"
cd /mnt/
echo "Perform write operation on the floppy disk"
echo "Creating a file Sample.txt"
echo "This is a sample file been created for testing..." >Sample.txt
sts=$?
if [ 0 -ne ${sts} ]; then
	echoerr "Unable to create a file on the Floppy Disk"
    exit 1
else
    echo  "Sample.txt file created successfully on the Floppy disk"
fi

echo "Perform read operation on the floppy disk"
cat Sample.txt
sts=$?
       if [ 0 -ne ${sts} ]; then
			echoerr "Unable to read Sample.txt file from the floppy disk"
		    exit 1
        else
            echo "Sample.txt file is read successfully from the Floppy disk"
       fi

echo "Perform delete operation on the Floppy disk"

rm Sample.txt
sts=$?

        if [ 0 -ne ${sts} ]; then
			echoerr "Unable to delete Sample.txt file from the floppy disk"
		    exit 1
        else
           echo "Sample.txt file is deleted successfully from the Floppy disk"
       fi

echo "#### Unmount the floppy disk ####"
cd ~
umount /mnt/
sts=$?
        if [ 0 -ne ${sts} ]; then
			echoerr "Unable to unmount the floppy disk"
		    exit 1
        else
            echo  "Floppy disk unmounted successfully"
        fi

echo "#########################################################"
echo "Result : Test Completed Succesfully"
