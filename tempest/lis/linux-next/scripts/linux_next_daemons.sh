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
set -e
set -x

LINUX_VERSION=$(uname -r)

cd /mnt/

#
# Start the testing
#
echo "KernelRelease=${LINUX_VERSION}"
echo "$(uname -a)"

LinuxRelease()
{
    DISTRO=$(grep -ihs "buntu\|Suse\|Fedora\|Debian\|CentOS\|Red Hat Enterprise Linux" /etc/{issue,*release,*version})

    case $DISTRO in
        *buntu*)
            echo "UBUNTU";;
        Fedora*)
            echo "FEDORA";;
        Cent??*6*)
            echo "CENTOS6";;
        Cent??*7*)
            echo "CENTOS7";;
        *SUSE*)
            echo "SLES";;
        *Red*Hat*)
            echo "RHEL";;
        Debian*)
            echo "DEBIAN";;
        *)
            echo "Error: Distro not supported!";;
    esac
}

ConfigRhel()
{
    cd linux-next/tools/hv/
        if [ $? -ne 0 ]; then
            echo "Error: Hv folder does not exist!"
            exit 1
        fi
    sudo mkdir -p /usr/include/uapi/linux/
         if [ $? -ne 0 ]; then
            echo "Error: Unable to create linux folder."
         fi
    sudo cp /mnt/linux-next/include/linux/hyperv.h /usr/include/linux
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hyper.h to /usr/include/linux."
            exit 1
        fi
    sudo cp /mnt/linux-next/include/uapi/linux/hyperv.h /usr/include/uapi/linux/
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hyperv.h to /usr/include/uapi/linux."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_kvp_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add hyperv.h in hv-kvp-daemon."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_vss_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add hyperv.h in hv-vss-daemon."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_fcopy_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add hyperv.h in hv-fcopy-daemon."
            exit 1
        fi

    echo "Info: Compiling daemons..."
    sudo make
        if [ $? -ne 0 ]; then
            echo "Error: Unable to compile daemons."
            exit 1
        fi
    sleep 5
    echo "Info: Daemons successfully compiled."

    sudo kill `ps -ef | grep hyperv | grep -v grep | awk '{print $2}'`
        if [ $? -ne 0 ]; then
            echo "Error: Unable to sudo kill daemons."
            exit 1
        fi
    if [[ $(systemctl list-units --type=service | grep hyperv) ]]; then
        echo "Running daemons are being stopped."
            sudo systemctl stop hypervkvpd.service
            if [ $? -ne 0 ]; then
                    echo "Error: Unable to stop hypervkvpd."
                    exit 1
            fi
            sudo systemctl stop hypervvssd.service
            if [ $? -ne 0 ]; then
                     echo "Error: Unable to stop hypervvssd."
                     exit 1
            fi
            sudo systemctl stop hypervfcopyd.service
             if [ $? -ne 0 ]; then
                    echo "Error: Unable to stop hypervfcopyd."
                    exit 1
            fi
        echo "Running daemons stopped."
    fi
    echo "Backing up default daemons."

    yes | sudo cp /usr/sbin/hypervkvpd /usr/sbin/hypervkvpd.old
        if [ $? -ne 0 ]; then
            echo "Warning: Unable to copy hv-kvp-daemon."
        fi
    yes | sudo cp /usr/sbin/hypervvssd /usr/sbin/hypervvssd.old
        if [ $? -ne 0 ]; then
             echo "Warning: Unable to copy hv-vss-daemon."
        fi
    yes | sudo cp /usr/sbin/hypervfcopyd /usr/sbin/hypervfcopyd.old
        if [ $? -ne 0 ]; then
            echo "Warning: Unable to copy hv-fcopy-daemon."
        fi
    echo "Default daemons back up."
    echo "Copying compiled daemons."
    yes | sudo mv hv_kvp_daemon /usr/sbin/hypervkvpd
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hv-kvp-daemon compiled."
            exit 1
        fi
    yes | sudo mv hv_vss_daemon /usr/sbin/hypervvssd
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hv-vss-daemon compiled."
            exit 1
        fi
    yes | sudo mv hv_fcopy_daemon /usr/sbin/hypervfcopyd
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hv-kvp-daemon compiled."
            exit 1
        fi
    echo "Compiled daemons copied."
    sudo sed -i 's,ExecStart=/usr/sbin/hypervkvpd,ExecStart=/usr/sbin/hypervkvpd -n,' /usr/lib/systemd/system/hypervkvpd.service
        if [ $? -ne 0 ]; then
            echo "Error: Unable to modify hv-kvp-daemon."
            exit 1
        fi
    sudo sed -i 's,ExecStart=/usr/sbin/hypervvssd,ExecStart=/usr/sbin/hypervvssd -n,' /usr/lib/systemd/system/hypervvssd.service
        if [ $? -ne 0 ]; then
            echo "Error: Unable to modify hv-vss-daemon."
            exit 1
        fi
    sudo sed -i 's,ExecStart=/usr/sbin/hypervfcopyd,ExecStart=/usr/sbin/hypervfcopyd -n,' /usr/lib/systemd/system/hypervfcopyd.service
        if [ $? -ne 0 ]; then
            echo "Error: Unable to modify hv-fcopy-daemon."
            exit 1
        fi

    sudo systemctl daemon-reload
        if [ $? -ne 0 ]; then
            echo "Error: Unable to reload daemon."
            exit 1
        fi
    sudo systemctl start hypervkvpd.service
        if [ $? -ne 0 ]; then
            echo "Error: Unable to start hv-kvp-daemon."
            exit 1
        fi
    sudo systemctl start hypervvssd.service
        if [ $? -ne 0 ]; then
            echo "Error: Unable to start hv-vss-daemon."
            exit 1
        fi
    sudo systemctl start hypervfcopyd.service
        if [ $? -ne 0 ]; then
            echo "Error: Unable to start hv-fcopy-daemon."
            exit 1
        fi
    echo "Daemons started."

    echo "Result : Test Completed Successfully"
    exit 0
}

ConfigSles()
{
    cd linux-next/tools/hv/
    sudo mkdir -p /usr/include/uapi/linux/
        if [ $? -ne 0 ]; then
            echo "Error: unable to create  /usr/include/uapi/linux/ folder."
            exit 1
        fi
    sudo cp /mnt/linux-next/include/linux/hyperv.h /usr/include/linux
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hyper.h to /usr/include/linux."
            exit 1
        fi
    sudo cp /mnt/linux-next/include/uapi/linux/hyperv.h /usr/include/uapi/linux/
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hyperv.h to /usr/include/uapi/linux."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_vss_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add library in hv_vss_daemon."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_kvp_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add library hv_kvp_daemon."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_fcopy_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add library hv_fcopy_daemon."
            exit 1
        fi
    echo "Compiling daemons."
    sudo make
        if [ $? -ne 0 ]; then
            echo "Error: Unable to compile daemons."
            exit 1
        fi
    sleep 5
    echo "Daemons compiled."

    sudo kill `ps -ef | grep hv | grep daemon | awk '{print $2}'`

    echo "Backing up default daemons."
    yes | sudo cp /usr/lib/hyper-v/bin/hv_kvp_daemon /usr/lib/hyper-v/bin/hv_kvp_daemon.old
        if [ $? -ne 0 ]; then
            echo "Warning: Unable to back up hv_kvp_daemon."
        fi
    yes | sudo cp /usr/lib/hyper-v/bin/hv_vss_daemon /usr/lib/hyper-v/bin/hv_vss_daemon.old
        if [ $? -ne 0 ]; then
            echo "Warning: Unable to back up hv_vss_daemon."
        fi
    yes | sudo cp /usr/lib/hyper-v/bin/hv_fcopy_daemon /usr/lib/hyper-v/bin/hv_fcopy_daemon.old
        if [ $? -ne 0 ]; then
            echo "Warning: Unable to back up hv_fcopy_daemon."
        fi
    echo "Default daemons back up."
    echo "Copying compiled daemons."


    yes | sudo cp hv_kvp_daemon  /usr/lib/hyper-v/bin/hv_kvp_daemon
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy compiled hv_kvp_daemon."
            exit 1
        fi
    yes | sudo cp hv_vss_daemon  /usr/lib/hyper-v/bin/hv_vss_daemon
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy compiled hv_vss_daemon."
            exit 1
        fi
    yes | sudo cp hv_fcopy_daemon /usr/lib/hyper-v/bin/hv_fcopy_daemon
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy compiled hv_fcopy_daemon."
            exit 1
        fi
    echo "Compiled daemons copied."
    systemctl daemon-reload
        if [ $? -ne 0 ]; then
            echo "Error: Unable to reload daemons."
            exit 1
        fi
    if [ -d /run/hv_kvp_daemon ]; then
        echo "Directory exists."
        rm -rf /run/hv_kvp_daemon
            if [ $? -eq 0 ]; then
                echo "Directory erased."
                sudo systemctl start hv_kvp_daemon.service
                    if [ $? -ne 0 ]; then
                        echo "Error: Unable to start hv-kvp-daemon."
                        exit 1
                    fi
            fi
    fi

    if [ -d /run/hv_vss_daemon ]; then
        echo "Directory exists."
        rm -rf /run/hv_vss_daemon
            if [ $? -eq 0 ]; then
                echo "Directory erased."
                sudo systemctl start hv_vss_daemon.service
                    if [ $? -ne 0 ]; then
                        echo "Error: Unable to start hv-kvp-daemon."
                        exit 1
                    fi
            fi
    fi

    if [ -d /run/hv_fcopy_daemon ]; then
        echo "Directory exists."
        rm -rf /run/hv_fcopy_daemon
            if [ $? -eq 0 ]; then
                echo "Directory erased."
                sudo systemctl start hv_fcopy_daemon.service
                    if [ $? -ne 0 ]; then
                        echo "Error: Unable to start hv-kvp-daemon."
                        exit 1
                    fi
            fi
    else
        echo "Folder doesn't exist."
    fi

    echo "Info: Daemons started."
    echo "Result : Test Completed Successfully"
    exit 0
}

ConfigCentos()
{
    cd linux-next/tools/hv/
        if [ $? -ne 0 ]; then
            echo "Error: Hv folder is not present."
            exit 1
        fi
    sudo mkdir -p /usr/include/uapi/linux/
         if [ $? -ne 0 ]; then
            echo "Error: Unable to create linux folder."
         fi
    sudo cp /mnt/linux-next/include/linux/hyperv.h /usr/include/linux
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hyper.h to /usr/include/linux."
            exit 1
        fi
    sudo cp /mnt/linux-next/include/uapi/linux/hyperv.h /usr/include/uapi/linux/
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hyperv.h to /usr/include/uapi/linux."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_kvp_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add hyperv.h in hv-kvp-daemon."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_vss_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add hyperv.h in hv-vss-daemon."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_fcopy_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add hyperv.h in hv-fcopy-daemon."
            exit 1
        fi
    echo "Compiling daemons."
    sudo make
        if [ $? -ne 0 ]; then
            echo "Error: Unable to compile the LIS daemons."
            exit 1
        fi
    sleep 5
    echo "Daemons compiled."

    sudo kill `ps -ef | grep daemon | grep -v grep | awk '{print $2}'`
        if [ $? -ne 0 ]; then
            echo "Error: Unable to sudo kill daemons."
            exit 1
        fi
    if [[ $(service --status -all | grep _daemon) ]]; then
        echo "Running daemons are being stopped."
            sudo service hypervkvpd stop
            if [ $? -ne 0 ]; then
                    echo "Error: Unable to stop hypervkvpd."
                    exit 1
            fi
            sudo service hypervvssd stop
            if [ $? -ne 0 ]; then
                     echo "Error: Unable to stop hypervvssd."
                     exit 1
            fi
            sudo service hypervfcopyd stop
             if [ $? -ne 0 ]; then
                    echo "Error: Unable to stop hypervfcopyd."
                    exit 1
            fi
        echo "Running daemons stopped."
    fi
    echo "Backing up default daemons."

    yes | sudo cp /usr/sbin/hv_kvp_daemon /usr/sbin/hv_kvp_daemon.old
        if [ $? -ne 0 ]; then
            echo "Warning: Unable to copy hv-kvp-daemon."
        fi
    yes | sudo cp /usr/sbin/hv_vss_daemon /usr/sbin/hv_vss_daemon.old
        if [ $? -ne 0 ]; then
             echo "Warning: Unable to copy hv-vss-daemon."
        fi
    yes | sudo cp /usr/sbin/hv_fcopy_daemon /usr/sbin/hv_fcopy_daemon.old
        if [ $? -ne 0 ]; then
            echo "Warning: Unable to copy hv-fcopy-daemon."
        fi
    echo "Default daemons back up."
    echo "Copying compiled daemons."
    yes | sudo mv hv_kvp_daemon /usr/sbin/
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hv-kvp-daemon compiled."
            exit 1
        fi
    yes | sudo mv hv_vss_daemon /usr/sbin/
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hv-vss-daemon compiled."
            exit 1
        fi
    yes | sudo mv hv_fcopy_daemon /usr/sbin/
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hv-kvp-daemon compiled."
            exit 1
        fi
    echo "Compiled daemons copied."

    sudo service hypervkvpd start
        if [ $? -ne 0 ]; then
            echo "Error: Unable to start hv-kvp-daemon."
            exit 1
        fi
    sudo service hypervvssd start
        if [ $? -ne 0 ]; then
            echo "Error: Unable to start hv-vss-daemon."
            exit 1
        fi
    sudo service hypervfcopyd start
        if [ $? -ne 0 ]; then
            echo "Error: Unable to start hv-fcopy-daemon."
            exit 1
        fi
    echo "Daemons started."

    echo "Result : Test Completed successfully"
    exit 0
}

ConfigUbuntu()
{
    cd /mnt/linux-next/tools/hv/
        if [ $? -ne 0 ]; then
            echo "Error: Hv folder is not created."
        fi
    sudo mkdir -p /usr/include/uapi/linux/
        if [ $? -ne 0 ]; then
            echo "Error: Unable to create linux directory."
            exit 1
        fi
    sudo cp /mnt/linux-next/include/linux/hyperv.h /usr/include/linux
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hyper.v to /usr/include/linux."
            exit 1
        fi
    sudo cp /mnt/linux-next/include/uapi/linux/hyperv.h /usr/include/uapi/linux/
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy hyperv.h to /usr/include/uapi/linux."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_kvp_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add hyperv.h library."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_vss_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add hyperv.h library."
            exit 1
        fi
    sudo sed -i 's,#include <linux/hyperv.h>,#include <uapi/linux/hyperv.h>,' hv_fcopy_daemon.c
        if [ $? -ne 0 ]; then
            echo "Error: Unable to add hyperv.h library."
            exit 1
        fi
    echo "Compiling daemons."
    sudo make
         if [ $? -ne 0 ]; then
            echo "Error: Unable to compile the LIS daemons!"
            exit 1
        fi
    sleep 5
    echo "Info: Daemons compiled."

    echo "Backing up default daemons."
    yes | sudo cp /usr/sbin/hv_kvp_daemon /usr/sbin/hv_kvp_daemon.old
        if [ $? -ne 0 ]; then
            echo "Warning: Unable to back up hv-kvp-daemon."
        fi
    yes | sudo cp /usr/sbin/hv_vss_daemon /usr/sbin/hv_vss_daemon.old
        if [ $? -ne 0 ]; then
            echo "Warning: Unable to back up hv-vss-daemon."
        fi
    yes | sudo cp /usr/sbin/hv_fcopy_daemon /usr/sbin/hv_fcopy_daemon.old
        if [ $? -ne 0 ]; then
            echo "Warning: Unable to back up hv-fcopy-daemon."
        fi
    echo "Default daemons backed up."
    echo "Copying compiled daemons."

    yes | sudo cp hv_kvp_daemon  /usr/sbin/hv_kvp_daemon
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy compiled hv_kvp_daemon."
            exit 1
        fi
    yes | sudo cp hv_vss_daemon  /usr/sbin/hv_vss_daemon
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy compiled hv_vss_daemon."
            exit 1
        fi
    yes | sudo cp hv_fcopy_daemon /usr/sbin/hv_fcopy_daemon
        if [ $? -ne 0 ]; then
            echo "Error: Unable to copy compiled hv_fcopy_daemon."
            exit 1
        fi

    echo "Compiled daemons copied."
    sudo systemctl daemon-reload
        if [ $? -ne 0 ]; then
            echo "Error: Unable to reload daemons."
            exit 1
        fi
    sudo systemctl start hv-kvp-daemon.service
        if [ $? -ne 0 ]; then
            echo "Error: Unable to start daemons."
            exit 1
        fi
    sudo systemctl start hv-vss-daemon.service
        if [ $? -ne 0 ]; then
            echo "Error: Unable to start hv_vss_daemon."
            exit 1
        fi
    sudo systemctl start hv-fcopy-daemon.service
        if [ $? -ne 0 ]; then
            echo "Error: Unable to start hv-fcopy-daemon."
            exit 1
        fi
    echo "Info: LIS daemons started."

    echo "Result : Test Completed successfully"
    exit 0
}

if [ -d "/mnt/net-next" ]; then
    ln -s /mnt/net-next/ /mnt/linux-next
fi

case $(LinuxRelease) in
    "DEBIAN" | "UBUNTU")
        ConfigUbuntu
    ;;

    "CENTOS6")
        ConfigCentos
    ;;

    "RHEL" | "CENTOS7")
        ConfigRhel
    ;;

    "SLES")
        ConfigSles
    ;;

    *)
       echo "Error: Distro '${distro}' not supported."
       exit 1
    ;;
esac
