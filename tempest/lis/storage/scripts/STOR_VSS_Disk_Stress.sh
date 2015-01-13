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

# Download iOzoneiozone3_430.tar
iOzoneVers='3_430'
curl http://www.iozone.org/src/current/iozone$iOzoneVers.tar > iozone$iOzoneVers.tar
sts=$?
if [ 0 -ne ${sts} ]; then
    echoerr "iOzone v$iOzoneVers download: Failed"
    exit 1
else
    echo "iOzone v$iOzoneVers download: Success"
fi


# Make sure the iozone exists
IOZONE=iozone$iOzoneVers.tar
if [ ! -e ${IOZONE} ];
then
    echoerr "Cannot find iozone file."
    exit 1
fi

sudo yum groupinstall "Development Tools" -y

# Get Root Directory of tarball
tarballdir=`sudo tar -tvf ${IOZONE} | head -n 1 | awk -F " " '{print $6}' | awk -F "/" '{print $1}'`

# Now Extract the Tar Ball.
sudo tar -xvf ${IOZONE}
sts=$?
if [ 0 -ne ${sts} ]; then
	echoerr "Failed to extract Iozone tarball"
	exit 1
fi


# cd in to directory
if [ !  ${tarballdir} ];
then
    echoerr "Cannot find tarballdir."
    exit 1
fi

cd ${tarballdir}/src/current

# Compile iOzone
sudo make linux
sts=$?
if [ 0 -ne ${sts} ]; then
    echoerr "make linux : Failed"
    exit 1
else
    echo "make linux : Sucsess"

fi

# Run Iozone
while true ; do ./iozone -ag 10G   ; done > /dev/null 2>&1 &
sts=$?
if [ 0 -ne ${sts} ]; then
    echoerr " Running IoZone  : Failed"
    exit 1
else
    echo " Running Iozone : Sucsess"
fi

