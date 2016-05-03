#!/bin/bash
#######################################################################
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
#######################################################################

#######################################################################
#
# InstallLisNext.sh
#
# Clone the Lis-Next reporitory from github, then build and
# install LIS from the source code.
#
#######################################################################


#######################################################################
#
# Main script body
#
#######################################################################

echoerr() { echo "$@" 1>&2; }
#
# If there is a lis-next directory, delete it since it should not exist.
#
if [ -e ./lis-next ]; then
    echo "Info : Removing an old lis-next directory"
    rm -rf ./lis-next
fi

#
# Clone Lis-Next
#

sudo yum groupinstall "Development Tools" -y
if [ $? -ne 0 ]; then
    echoerr "Error: unable to install Development Tools"
    exit 1
fi


sudo yum install kernel-devel -y
if [ $? -ne 0 ]; then
    echoerr "Error: unable to install kernel-devel"
    exit 1
fi

sudo yum install git -y
if [ $? -ne 0 ]; then
    echoerr "Error: unable to install git"
    exit 1
fi

echo "Info : Cloning lis-next"
git clone https://github.com/LIS/lis-next
if [ $? -ne 0 ]; then
    echoerr "Error: unable to clone lis-next"
    exit 1
fi

#
# Figure out what version of CentOS/RHEL we are running
#

GetDistro()
{
    # Make sure we don't inherit anything
    declare __DISTRO
    #Get distro (snipper take from alsa-info.sh)
    __DISTRO=$(grep -ihs "Ubuntu\|SUSE\|Fedora\|Debian\|CentOS\|Red Hat Enterprise Linux" /etc/{issue,*release,*version})
    case $__DISTRO in
        *CentOS*5.*)
            DISTRO=centos_5
            ;;
        *CentOS*6.*)
            DISTRO=centos_6
            ;;
        *CentOS*7*)
            DISTRO=centos_7
            ;;
        *CentOS*)
            DISTRO=centos_x
            ;;
        *Red*5.*)
            DISTRO=redhat_5
            ;;
        *Red*6.*)
            DISTRO=redhat_6
            ;;
        *Red*7*)
            DISTRO=redhat_7
            ;;
        *Red*)
            DISTRO=redhat_x
            ;;
        *)
            DISTRO=unknown
            return 1
            ;;
    esac

    return 0
}

rhel_version=0
GetDistro
echo "Info : Detected OS distro/version ${DISTRO}"

case $DISTRO in
redhat_7|centos_7)
    rhel_version=7
    ;;
redhat_6|centos_6)
    rhel_version=6
    ;;
redhat_5|centos_5)
    rhel_version=5
    ;;
*)
    echoerr "Error: Unknow or unsupported version: ${DISTRO}"
    exit 1
    ;;
esac

echo "Info : Building ${rhel_version}.x source tree"
cd lis-next/hv-rhel${rhel_version}.x/hv
sudo ./rhel${rhel_version}-hv-driver-install
if [ $? -ne 0 ]; then
    echoerr "Error: Unable to build the lis-next RHEL ${rhel_version} code"
    exit 1
fi

echo "Info: Successfully built lis-next from the hv-rhel-${rhel_version}.x code"

# Compiling daemons
cd ./tools

sudo make
if [ $? -ne 0 ]; then
    echoerr "Error: Unable to compile the LIS modules!"
    exit 1
fi

# Stopping selinux
sudo setenforce 0
sudo sed -i -e 's/SELINUX=enforcing/SELINUX=disabled/g' /etc/selinux/config

case "$DISTRO" in
redhat_7|centos_7)
	if [[ $(systemctl list-units --type=service | grep hyperv) ]]; then
			echo "Running daemons are being stopped."
				sudo systemctl stop hypervkvpd.service
				if [ $? -ne 0 ]; then
						echoerr "Error: Unabele to stop hypervkvpd."
						exit 1
				fi
				sudo systemctl stop hypervvssd.service
				if [ $? -ne 0 ]; then
						 echoerr "Error: Unable to stop hypervvssd."
						 exit 1
				fi
				sudo systemctl stop hypervfcopyd.service
				 if [ $? -ne 0 ]; then
						echoerr "Error: Unable to stop hypervfcopyd."
						exit 1
				fi
			echo "Running daemons have been stopped."
	fi

	echo "Backing up default daemons."

	sudo \cp /usr/sbin/hypervkvpd /usr/sbin/hypervkvpd.old
		if [ $? -ne 0 ]; then
			echoerr "Error: Unable to copy hv-kvp-daemon."
			exit 1
		fi
	sudo \cp /usr/sbin/hypervvssd /usr/sbin/hypervvssd.old
		if [ $? -ne 0 ]; then
			echoerr "Error: Unable to copy hv-vss-daemon."
			exit 1
		fi
	sudo \cp /usr/sbin/hypervfcopyd /usr/sbin/hypervfcopyd.old
		if [ $? -ne 0 ]; then
			echoerr "Error: Unable to copy hv-fcopy-daemon."
			exit 1
		fi

	echo "Default daemons back up."
	echo "Copying compiled daemons."
	sudo mv -f hv_kvp_daemon /usr/sbin/hypervkvpd
	if [ $? -ne 0 ]; then
		echoerr "Error: Unable to copy hv-kvp-daemon compiled."
		exit 1
	fi

	sudo mv -f hv_vss_daemon /usr/sbin/hypervvssd
	if [ $? -ne 0 ]; then
		echoerr "Error: Unable to copy hv-vss-daemon compiled."
		exit 1
	fi

	sudo mv -f hv_fcopy_daemon /usr/sbin/hypervfcopyd
	if [ $? -ne 0 ]; then
		echoerr "Error: Unable to copy hv-kvp-daemon compiled."
		exit 1
	fi

	echo "Compiled daemons copied."

	sudo sed -i 's,ExecStart=/usr/sbin/hypervkvpd,ExecStart=/usr/sbin/hypervkvpd -n,' /usr/lib/systemd/system/hypervkvpd.service
		if [ $? -ne 0 ]; then
			echoerr "Error: Unable to modify hv-kvp-daemon."
			exit 1
		fi
	sudo sed -i 's,ExecStart=/usr/sbin/hypervvssd,ExecStart=/usr/sbin/hypervvssd -n,' /usr/lib/systemd/system/hypervvssd.service
		if [ $? -ne 0 ]; then
			echoerr "Error: Unable to modify hv-vss-daemon."
			exit 1
		fi
	sudo sed -i 's,ExecStart=/usr/sbin/hypervfcopyd,ExecStart=/usr/sbin/hypervfcopyd -n,' /usr/lib/systemd/system/hypervfcopyd.service
		if [ $? -ne 0 ]; then
			echoerr "Error: Unable to modify hv-fcopy-daemon."
			exit 1
		fi

	sudo systemctl daemon-reload
		if [ $? -ne 0 ]; then
			echoerr "Error: Unable to reload daemon."
			exit 1
		fi
	sudo systemctl start hypervkvpd.service
		if [ $? -ne 0 ]; then
			echoerr "Error: Unable to start hv-kvp-daemon."
			exit 1
		fi
	sudo systemctl start hypervvssd.service
		if [ $? -ne 0 ]; then
			echoerr "Error: Unable to start hv-vss-daemon."
			exit 1
		fi
	sudo systemctl start hypervfcopyd.service
		if [ $? -ne 0 ]; then
			echoerr "Error: Unable to start hv-fcopy-daemon."
			exit 1
		fi
;;

redhat_6|centos_6)
	kill `ps -ef | grep daemon | grep -v grep | awk '{print $2}'`
        if [ $? -ne 0 ]; then
            echoerr "Error: Unable to kill daemons."
            exit 1
        fi

    if [[ $(service --status -all | grep _daemon) ]]; then
        echo "Running daemons are being stopped."
            sudo service hypervkvpd stop
            if [ $? -ne 0 ]; then
                    echoerr "Error: Unabele to stop hypervkvpd."
                    exit 1
            fi
            sudo service hypervvssd stop
            if [ $? -ne 0 ]; then
                     echoerr "Error: Unable to stop hypervvssd."
                     exit 1
            fi
            sudo service hypervfcopyd stop
             if [ $? -ne 0 ]; then
                    echoerr "Error: Unable to stop hypervfcopyd."
                    exit 1
            fi
        echo "Running daemons stopped."
    fi

    echo "Backing up default daemons."

    sudo \cp /usr/sbin/hv_kvp_daemon /usr/sbin/hv_kvp_daemon.old
        if [ $? -ne 0 ]; then
            echoerr "Error: Unable to copy hv-kvp-daemon."
            exit 1
        fi
    sudo \cp /usr/sbin/hv_vss_daemon /usr/sbin/hv_vss_daemon.old
        if [ $? -ne 0 ]; then
             echoerr "Error: Unable to copy hv-vss-daemon."
            exit 1
        fi
    sudo \cp /usr/sbin/hv_fcopy_daemon /usr/sbin/hv_fcopy_daemon.old
        if [ $? -ne 0 ]; then
            echoerr "Error: Unable to copy hv-fcopy-daemon."
            exit 1
        fi

    echo "Default daemons back up."
    echo "Copying compiled daemons."
    sudo mv -f hv_kvp_daemon /usr/sbin/
        if [ $? -ne 0 ]; then
            echoerr "Error: Unable to copy hv-kvp-daemon compiled."
            exit 1
        fi
    sudo mv -f hv_vss_daemon /usr/sbin/
        if [ $? -ne 0 ]; then
            echoerr "Error: Unable to copy hv-vss-daemon compiled."
            exit 1
        fi
    sudo mv -f hv_fcopy_daemon /usr/sbin/
        if [ $? -ne 0 ]; then
            echoerr "Error: Unable to copy hv-kvp-daemon compiled."
            exit 1
        fi

    echo "Compiled daemons copied."

    sudo service hypervkvpd start
        if [ $? -ne 0 ]; then
            echoerr "Error: Unable to start hv-kvp-daemon."
            exit 1
        fi
    sudo service hypervvssd start
        if [ $? -ne 0 ]; then
            echoerr "Error: Unable to start hv-vss-daemon."
            exit 1
        fi
    sudo service hypervfcopyd start
        if [ $? -ne 0 ]; then
            echoerr "Error: Unable to start hv-fcopy-daemon."
            exit 1
        fi

    echo "Daemons started."
;;
esac

echo "Info: Successfully compiled and started the lis-next tree LIS daemons."

# work-around just to satisfy requirements
sudo yum install numactl -y

#
# If we got here, everything worked.
# Let LISA know
#
echo "Exiting with state: TestCompleted."

exit 0
