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

declare os_VENDOR os_RELEASE os_UPDATE os_PACKAGE os_CODENAME
maxdelay=5.0 # max offset in seconds.

# GetOSVersion
function GetOSVersion {

    # Figure out which vendor we are
    if [[ -x "`which sw_vers 2>/dev/null`" ]]; then
        # OS/X
        os_VENDOR=`sw_vers -productName`
        os_RELEASE=`sw_vers -productVersion`
        os_UPDATE=${os_RELEASE##*.}
        os_RELEASE=${os_RELEASE%.*}
        os_PACKAGE=""
        if [[ "$os_RELEASE" =~ "10.7" ]]; then
            os_CODENAME="lion"
        elif [[ "$os_RELEASE" =~ "10.6" ]]; then
            os_CODENAME="snow leopard"
        elif [[ "$os_RELEASE" =~ "10.5" ]]; then
            os_CODENAME="leopard"
        elif [[ "$os_RELEASE" =~ "10.4" ]]; then
            os_CODENAME="tiger"
        elif [[ "$os_RELEASE" =~ "10.3" ]]; then
            os_CODENAME="panther"
        else
            os_CODENAME=""
        fi
    elif [[ -x $(which lsb_release 2>/dev/null) ]]; then
        os_VENDOR=$(lsb_release -i -s)
        os_RELEASE=$(lsb_release -r -s)
        os_UPDATE=""
        os_PACKAGE="rpm"
        if [[ "Debian,Ubuntu,LinuxMint" =~ $os_VENDOR ]]; then
            os_PACKAGE="deb"
        elif [[ "SUSE LINUX" =~ $os_VENDOR ]]; then
            lsb_release -d -s | grep -q openSUSE
            if [[ $? -eq 0 ]]; then
                os_VENDOR="openSUSE"
            fi
        elif [[ $os_VENDOR == "openSUSE project" ]]; then
            os_VENDOR="openSUSE"
        elif [[ $os_VENDOR =~ Red.*Hat ]]; then
            os_VENDOR="Red Hat"
        fi
        os_CODENAME=$(lsb_release -c -s)
    elif [[ -r /etc/redhat-release ]]; then
        # Red Hat Enterprise Linux Server release 5.5 (Tikanga)
        # Red Hat Enterprise Linux Server release 7.0 Beta (Maipo)
        # CentOS release 5.5 (Final)
        # CentOS Linux release 6.0 (Final)
        # Fedora release 16 (Verne)
        # XenServer release 6.2.0-70446c (xenenterprise)
        os_CODENAME=""
        for r in "Red Hat" CentOS Fedora XenServer; do
            os_VENDOR=$r
            if [[ -n "`grep \"$r\" /etc/redhat-release`" ]]; then
                ver=`sed -e 's/^.* \([0-9].*\) (\(.*\)).*$/\1\|\2/' /etc/redhat-release`
                os_CODENAME=${ver#*|}
                os_RELEASE=${ver%|*}
                os_UPDATE=${os_RELEASE##*.}
                os_RELEASE=${os_RELEASE%.*}
                break
            fi
            os_VENDOR=""
        done
        os_PACKAGE="rpm"
    elif [[ -r /etc/SuSE-release ]]; then
        for r in openSUSE "SUSE Linux"; do
            if [[ "$r" = "SUSE Linux" ]]; then
                os_VENDOR="SUSE LINUX"
            else
                os_VENDOR=$r
            fi

            if [[ -n "`grep \"$r\" /etc/SuSE-release`" ]]; then
                os_CODENAME=`grep "CODENAME = " /etc/SuSE-release | sed 's:.* = ::g'`
                os_RELEASE=`grep "VERSION = " /etc/SuSE-release | sed 's:.* = ::g'`
                os_UPDATE=`grep "PATCHLEVEL = " /etc/SuSE-release | sed 's:.* = ::g'`
                break
            fi
            os_VENDOR=""
        done
        os_PACKAGE="rpm"
    # If lsb_release is not installed, we should be able to detect Debian OS
    elif [[ -f /etc/debian_version ]] && [[ $(cat /proc/version) =~ "Debian" ]]; then
        os_VENDOR="Debian"
        os_PACKAGE="deb"
        os_CODENAME=$(awk '/VERSION=/' /etc/os-release | sed 's/VERSION=//' | sed -r 's/\"|\(|\)//g' | awk '{print $2}')
        os_RELEASE=$(awk '/VERSION_ID=/' /etc/os-release | sed 's/VERSION_ID=//' | sed 's/\"//g')
    fi
    export os_VENDOR os_RELEASE os_UPDATE os_PACKAGE os_CODENAME
}

# Determine if current distribution is a Fedora-based distribution
# (Fedora, RHEL, CentOS, etc).
# is_fedora
function is_fedora {
    if [[ -z "$os_VENDOR" ]]; then
        GetOSVersion
    fi

    [ "$os_VENDOR" = "Fedora" ] || [ "$os_VENDOR" = "Red Hat" ] || \
        [ "$os_VENDOR" = "CentOS" ] || [ "$os_VENDOR" = "OracleServer" ]
}

# Determine if current distribution is a SUSE-based distribution
# (openSUSE, SLE).
# is_suse
function is_suse {
    if [[ -z "$os_VENDOR" ]]; then
        GetOSVersion
    fi

    [ "$os_VENDOR" = "openSUSE" ] || [ "$os_VENDOR" = "SUSE LINUX" ]
}

# Determine if current distribution is an Ubuntu-based distribution
# It will also detect non-Ubuntu but Debian-based distros
# is_ubuntu
function is_ubuntu {
    if [[ -z "$os_PACKAGE" ]]; then
        GetOSVersion
    fi
    [ "$os_PACKAGE" = "deb" ]
}


echoerr() { echo "$@" 1>&2; }
echo "#### NTP time syncronization test ####"

# # Check if the timezone parameter is present
# if [[ -z $1 ]]; then
#     echoerr "ERROR: You must provide a TZONE variable as a parameter!"
#     # exit 10
# fi

# Check on what distro we are running
# rhel, centos, etc..
if is_fedora ; then
    # Check if ntpd is running. On Fedora based distros we have ntpstat.
    sudo ntpstat 1> /dev/null 2> /dev/null
    if [[ $? -ne 0 ]]; then
        echo "NTPD not installed. Trying to install ..."
        sudo yum install -y ntp ntpdate ntp-doc
        if [[ $? -ne 0 ]] ; then
            echoerr "ERROR: Unable to install ntpd. Aborting"
            exit 10
        fi
        sudo chkconfig ntpd on
        if [[ $? -ne 0 ]] ; then
            echoerr "ERROR: Unable to chkconfig ntpd on. Aborting"
            exit 10
        fi
        sudo ntpdate pool.ntp.org
        if [[ $? -ne 0 ]] ; then
            echoerr "ERROR: Unable to set ntpdate. Aborting"
            exit 10
        fi
        sudo service ntpd start
        if [[ $? -ne 0 ]] ; then
            echoerr "ERROR: Unable to start ntpd. Aborting"
            exit 10
        fi
        echo "NTPD installed suceccesfully!"
    fi
    # Restart NTPD
    sudo service ntpd restart
    if [[ $? -ne 0 ]]; then
        echoerr "ERROR: Unable to start ntpd. Aborting"
        exit 10
    fi

# ubuntu, debian
elif is_ubuntu ; then
    echo "BUBU: $os_VENDOR $os_RELEASE $os_CODENAME"
    # Check if ntp is running
    sudo ntpq -p 1> /dev/null 2> /dev/null
    if [[ $? -ne 0 ]]; then
        echo "NTP is not installed. Trying to install ..."
        sudo apt-get install ntp -y
        if [[ $? -ne 0 ]] ; then
            echoerr "ERROR: Unable to install ntp. Aborting"
            exit 10
        fi
        echo "NTP installed suceccesfully!"
    fi
    # Restart NTPD
    sudo service ntp restart
    if [[ $? -ne 0 ]]; then
        echoerr "ERROR: Unable to restart ntpd. Aborting"
        exit 10
    fi

elif is_suse ; then
    # TODO
    echo "SUSE: TBD"

# other distro's
else
    echoerr "Distro not suported. Aborting"
    exit 10
fi


# We wait 10 seconds for the ntp server to sync
sleep 10

# Now let's see if the VM is in sync with ntp server
sudo ntpq -p
if [[ $? -ne 0 ]]; then
    echoerr "Unable to query NTP daemon!"
    exit 10
fi
# loopinfo returns the offset between the ntp server and internal clock
delay=$(ntpdc -c loopinfo | awk 'NR==1 {print $2}')

# Using awk for float comparison
check=$(echo "$delay $maxdelay" | awk '{if ($1 < $2) print 0; else print 1}')

if [[ 0 -ne $check ]] ; then
    echoerr "ERROR: NTP Time out of sync. Test Failed"
    echo "NTP offset is $delay seconds."
    exit 10
fi

# If we reached this point, time is synced.
echo "NTP offset is $delay seconds."
echo "SUCCES: NTP time synced!"