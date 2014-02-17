#!/bin/bash
# Description:
#   This script was created to automate the testing of a Linux Integration services.
#   This sets the ntp time servers and checks the time difference.
#
#   ! NTP servers and timezone are hardcoded !
#
#   Current tested distros are:
#   RHEL 6
#   CENTOS 6
#   UBUBTU
#   SLES
#   DEBIAN 7
#
#   History:
#   Created by: v-dopasl@microsoft.com
#
################################################################



LinuxRelease()
# Checks what Linux distro we are running
{
    DISTRO=`grep -ihs "buntu\|Suse\|Fedora\|Debian\|CentOS\|Red Hat Enterprise Linux" /etc/{issue,*release,*version}`

    case $DISTRO in
        *buntu*)
            echo "UBUNTU";;
        Fedora*)
            echo "FEDORA";;
        CentOS*)
            echo "CENTOS";;
        *suse*)
            echo "SLES";;
        Red*Hat*)
            echo "RHEL";;
        Debian*)
            echo "DEBIAN";;
    esac
}


LogMsg()
{
    echo `date "+%a %b %d %T %Y"` : ${1}    # To add the timestamp to the log file
}



UpdateTestState()
{
    echo $1 > $HOME/state.txt
}

cd ~

if [ -e ~/summary.log ]; then
    LogMsg "Cleaning up previous copies of summary.log"
    rm -rf ~/summary.log
fi

UpdateSummary()
{
    echo $1 >> ~/summary.log
}

# if [ -e $HOME/constants.sh ]; then
# 	. $HOME/constants.sh
# else
# 	LogMsg "ERROR: Unable to source the constants file."
# 	UpdateTestState "TestAborted"
# 	exit 1
# fi

#
# Convert any .sh files to Unix format
#

#dos2unix -f ica/* > /dev/null  2>&1



LogMsg "########################################################"
LogMsg "This script tests NTP time syncronization"
LogMsg "VM is $(LinuxRelease) `uname`"

#
# Let's check if the NTP service is installed
#

service ntp restart 1> /dev/null 2> /dev/null
sts=$?
    if [ 0 -ne ${sts} ]; then
    service ntpd restart 1> /dev/null 2> /dev/null
    sts=$?
        if [ 0 -ne ${sts} ]; then
        LogMsg "No NTP service detected. Please install NTP before running this test"
        LogMsg "Aborting test."
        UpdateTestState "TestAborted"

        exit 1
        fi
    fi

#
# Now we set the corect timezone for the test. This is distro-specific
#
case $(LinuxRelease) in
    "DEBIAN" | "UBUNTU")
    sed -i 's#^Zone.*# Zone="America/Los_Angeles" #g' /etc/timezone
    sts=$?
        if [ 0 -ne ${sts} ]; then
            LogMsg "Unable to sed Zone: ${sts}"
            LogMsg "Aborting test."
            UpdateTestState "TestAborted"
            exit 1
        fi
    sed -i 's/^UTC.*/ UTC=False /g' /etc/timezone
    sts=$?
        if [ 0 -ne ${sts} ]; then
            LogMsg "Unable to sed UTC: ${sts}"
            LogMsg "Aborting test."
            UpdateTestState "TestAborted"
            exit 1
        fi
    # delete old localtime
    rm -f /etc/localtime
    #Create soft link.
    ln -s /usr/share/zoneinfo/America/Los_Angeles /etc/localtime
    sts=$?
        if [ 0 -ne ${sts} ]; then
            LogMsg "Unable to softlink: ${sts}"
            LogMsg "Aborting test."
            UpdateTestState "TestAborted"
            exit 1
        fi

        ;;

   #
   #
   #

    "CENTOS" | "SLES" | "RHEL")
    sed -i 's#^Zone.*# Zone="America/Los_Angeles" #g' /etc/sysconfig/clock
    sts=$?
        if [ 0 -ne ${sts} ]; then
            LogMsg "Unable to sed Zone: ${sts}"
            LogMsg "Aborting test."
            UpdateTestState "TestAborted"
            exit 1
        fi
    sed -i 's/^UTC.*/ UTC=False /g' /etc/sysconfig/clock
    sts=$?
        if [ 0 -ne ${sts} ]; then
            LogMsg "Unable to sed UTC: ${sts}"
            LogMsg "Aborting test."
            UpdateTestState "TestAborted"
            exit 1
        fi


    rm -f /etc/localtime # delete old localtime

    ln -s /usr/share/zoneinfo/America/Los_Angeles /etc/localtime # Create soft link.
    sts=$?
        if [ 0 -ne ${sts} ]; then
            LogMsg "Unable to softlink: ${sts}"
            LogMsg "Aborting test."
            UpdateTestState "TestAborted"
            exit 1
        fi
    ;;
    *)
    LogMsg "Distro not supported"
    UpdateTestState "TestAborted"
    UpdateSummary " Distro not supported, test aborted"
    exit 1
    ;;
esac

# server 172.31.79.142
# server 172.31.79.151
# server 172.31.79.186
# server 172.31.79.150
# server 172.31.79.144

#
# Edit NTP Server config and set the timeservers
#
sed -i 's/^server.*/ /g' /etc/ntp.conf
echo "
server 0.pool.ntp.org
server 1.pool.ntp.org
server 2.pool.ntp.org
server 3.pool.ntp.org
" >> /etc/ntp.conf
sts=$?
    if [ 0 -ne ${sts} ]; then
        LogMsg "Unable to sed Server: ${sts}"
	    LogMsg "Aborting test."
        UpdateTestState "TestAborted"
	    exit 1
    fi
#
# Restart ntp service.
#
service ntp restart 2> /dev/null
service ntpd restart 2> /dev/null

#
# Check if the timezone is set corectly
#
tz=`date +%Z`
sts=$?
if [[ $tz -ne "PST" ]]; then
    LogMsg "Failed to set timezone."
    LogMsg "Aborting test."
    UpdateTestState "TestFailed"
    exit 1
else
    LogMsg "Timezone is $tz and is set ok"
fi

#
# Now let's test if the VM is in sync with ntp server
#
ntpdc -p
sts=$?
    if [ 0 -ne ${sts} ]; then
        LogMsg "Unable to query NTP deamon: ${sts}"
	    LogMsg "Aborting test."
        UpdateTestState "TestAborted"
	    exit 1
    fi
a=`ntpdc -p | awk 'NR==3 {print $6}'`
LogMsg $a


if [[ $a < 5.00000 ]]; then
	LogMsg  "NTP Time synced"
	UpdateSummary " Timesync NTP: Success"
else
	LogMsg  "NTP Time out of sync"
	UpdateSummary " Timesync NTP: Failed"
	UpdateTestState "TestFailed"
fi

LogMsg "#########################################################"
LogMsg "Result : Test Completed Succesfully"
LogMsg "Exiting with state: TestCompleted."
UpdateTestState "TestCompleted"