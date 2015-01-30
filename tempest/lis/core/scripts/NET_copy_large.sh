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
SSH_PRIVATE_KEY=$1
USER=$2
STATIC_IP2=$3
echoerr() { echo "$@" 1>&2; }
cd ~
output_file='large_file'

#compute md5sum
local_md5sum=$(md5sum /tmp/$output_file | cut -f 1 -d ' ')

#send file to remote_vm
sudo scp -i /home/"$USER"/.ssh/"$SSH_PRIVATE_KEY" -v -o StrictHostKeyChecking=no /tmp/"$output_file" "$USER"@"$STATIC_IP2":/tmp/"$output_file"

if [ 0 -ne $? ]; then
    msg="Unable to copy file $output_file to $STATIC_IP2:/tmp/$output_file"
    echoerr "$msg"
    exit 10
fi

echo "Successfully sent $output_file to $STATIC_IP2:/tmp/$output_file"

# erase file locally, if set
sudo rm -f /tmp/"$output_file"

# copy file back from remote vm
sudo scp -i /home/"$USER"/.ssh/"$SSH_PRIVATE_KEY" -v -o StrictHostKeyChecking=no "$USER"@"$STATIC_IP2":/tmp/"$output_file" /tmp/"$output_file"

if [ 0 -ne $? ]; then
    msg="Unable to copy from $STATIC_IP2:$remote_home/$output_file"
    echoerr "$msg"
    exit 10
fi

echo "Received $outputfile from $STATIC_IP2"

# check md5sums
remote_md5sum=$(md5sum /tmp/$output_file | cut -f 1 -d ' ')

if [ "$local_md5sum" != "$remote_md5sum" ]; then
    msg="md5sums differ. Files do not match"
    echoerr "$msg"
    exit 10
fi

echo "Checksums of file match. Test successful"
exit 0