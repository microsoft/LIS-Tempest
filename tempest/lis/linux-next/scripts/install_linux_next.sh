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

#######################################################################
#
# The outputs are directed into files named:
#     Perf_BuildKernel_make.log,
#     Perf_BuildKernel_makemodulesinstall.log,
#     Perf_BuildKernel_makeinstall.log
#
#######################################################################

SOURCE_TYPE="ONLINE"
LINUX_KERNEL_LOCATION="git://git.kernel.org/pub/scm/linux/kernel/git/next/linux-next.git"
KERNEL_VERSION="linux-next"
OVERWRITE_DEFAULT_KERNEL=false

DEBUG_LEVEL=3
CONFIG_FILE=.config
LINUX_VERSION=$(uname -r)
START_DIR=$(pwd)

#######################################################################
# Adds a timestamp to the log file
#######################################################################
function LogMsg() {
    echo $(date "+%a %b %d %T %Y") : ${1}
}

dbgprint() {
    if [ $1 -le $DEBUG_LEVEL ]; then
        echo "$2"
    fi
}

ApplyPatchesAndCompile() {
    #
    # Create the .config file
    #
    dbgprint 1 "Creating the .config file."
    if [ -f ~/ica/kernel.config.base ]; then
        # Basing a new kernel config on a previous kernel config file will
        # provide flexibility in providing know good config files with certain
        # options enabled/disabled.  Functionality could also potentially be
        # added here for choosing between multiple old config files depending
        # on the distro that the kernel is being compiled on (i.g. if Fedora
        # is detected copy ~/ica/kernel.config.base-fedora to .config before
        # running 'make oldconfig')

        dbgprint 3 "Creating new config based on a previous .config file"
        cp ~/ica/kernel.config.base .config

        # Base the new config on the old one and select the default config
        # option for any new options in the newer kernel version
        yes "" | sudo make oldconfig
    else
        dbgprint 3 "Create a .config file from existing one"
        yes "" | sudo make oldconfig
        sts=$?
        if [ 0 -ne ${sts} ]; then
            dbgprint 0 "make defconfig failed."
            dbgprint 0 "Aborting the test."
            exit 60
        fi

        if [ ! -e ${CONFIG_FILE} ]; then
            dbgprint 0 "make defconfig did not create the '${CONFIG_FILE}'"
            dbgprint 0 "Aborting the test."
            exit 70
        fi

        #
        # Enable HyperV support
        #
        dbgprint 3 "Enabling HyperV support in the ${CONFIG_FILE}"
        # On this first 'sudo sed' command use --in-place=.orig to make a backup
        # of the original .config file created with 'defconfig'
        sudo sed --in-place=.orig -e s:"# CONFIG_HYPERVISOR_GUEST is not set":"CONFIG_HYPERVISOR_GUEST=m\nCONFIG_HYPERV=m\nCONFIG_HYPERV=m\nCONFIG_HYPERV_BALLOON=m\nCONFIG_HYPERV_STORAGE=m\nCONFIG_HYPERV_NET=m\nCONFIG_HYPERV_KEYBOARD=m\nCONFIG_FB_HYPERV=m\nCONFIG_HID_HYPERV_MOUSE=m": ${CONFIG_FILE}
        sudo sed --in-place -e s:"# CONFIG_HYPERVISOR_GUEST is not set":"CONFIG_HYPERVISOR_GUEST=m\nCONFIG_HYPERV=m\nCONFIG_HYPERV_UTILS=m\nCONFIG_HYPERV_BALLOON=m\nCONFIG_HYPERV_STORAGE=m\nCONFIG_HYPERV_NET=m\nCONFIG_HYPERV_KEYBOARD=m\nCONFIG_FB_HYPERV=m\nCONFIG_HID_HYPERV_MOUSE=m": ${CONFIG_FILE}

        # Disable kernel preempt support , because of this lot of stack trace is coming and some time kernel does not boot at all.
        #
        dbgprint 3 "Disabling KERNEL_PREEMPT_VOLUNTARY in ${CONFIG_FILE}"
        # On this first this is a workaround for known bug that makes kernel lockup once the bug is fixed we can remove this in PS bug ID is 124 and 125
        sudo sed --in-place -e s:"CONFIG_PREEMPT_VOLUNTARY=y":"# CONFIG_PREEMPT_VOLUNTARY is not set": ${CONFIG_FILE}

        #
        # Enable Ext4, Reiser support (ext3 is enabled by default)
        #
        sudo sed --in-place -e s:"# CONFIG_EXT4_FS is not set":"CONFIG_EXT4_FS=y\nCONFIG_EXT4_FS_XATTR=y\nCONFIG_EXT4_FS_POSIX_ACL=y\nCONFIG_EXT4_FS_SECURITY=y": ${CONFIG_FILE}
        sudo sed --in-place -e s:"# CONFIG_REISERFS_FS is not set":"CONFIG_REISERFS_FS=y\nCONFIG_REISERFS_PROC_INFO=y\nCONFIG_REISERFS_FS_XATTR=y\nCONFIG_REISERFS_FS_POSIX_ACL=y\nCONFIG_REISERFS_FS_SECURITY=y": ${CONFIG_FILE}

        #
        # Enable Tulip network driver support. This is needed for the "legacy"
        # network adapter provided by Hyper-V
        #
        sudo sed --in-place -e s:"# CONFIG_TULIP is not set":"CONFIG_TULIP=y\nCONFIG_TULIP_MMIO=y": ${CONFIG_FILE}

        #
        # Enable Hyper-V PCI passthrough. This is needed for the SR-IOV and
        # other PCI passthrough features.
        #
        sudo sed --in-place -e s:"# CONFIG_PCI_HYPERV is not set":"CONFIG_PCI_HYPERV=m": ${CONFIG_FILE}

        # Disable staging
        sudo sed --in-place -e s:"CONFIG_STAGING=y":"# CONFIG_STAGING is not set": ${CONFIG_FILE}

        # Disable module signing verification. This requires libSSL support if enabled.
        sudo sed --in-place -e s:"CONFIG_KEXEC_BZIMAGE_VERIFY_SIG=y":"# CONFIG_KEXEC_BZIMAGE_VERIFY_SIG is not set": ${CONFIG_FILE}
        sudo sed --in-place -e s:"CONFIG_MODULE_SIG=y":"# CONFIG_MODULE_SIG is not set": ${CONFIG_FILE}
        sudo sed --in-place -e s:"CONFIG_MODULE_SIG_SHA256=y":"# CONFIG_MODULE_SIG_SHA256 is not set": ${CONFIG_FILE}
        sudo sed --in-place -e s:"CONFIG_MODULE_SIG_HASH=.*":"": ${CONFIG_FILE}
        sudo sed --in-place -e s:"CONFIG_MODULE_SIG_KEY=.*":"": ${CONFIG_FILE}
        sudo sed --in-place -e s:"CONFIG_SYSTEM_TRUSTED_KEYRING=y":"# CONFIG_SYSTEM_TRUSTED_KEYRING is not set": ${CONFIG_FILE}
        sudo sed --in-place -e s:"CONFIG_SYSTEM_TRUSTED_KEYS=.*":"": ${CONFIG_FILE}

        yes "" | sudo make oldconfig

        # Workaround: Enable HyperV Sock functionality. Otherwise, yes "" | make oldconfig won't set this
        sudo sed --in-place -e s:"CONFIG_HYPERV_SOCK=.*":"": ${CONFIG_FILE}
        sudo echo "CONFIG_HYPERV_SOCK=m" >> ${CONFIG_FILE}
    fi
    echo "make oldconfig: Success"

    # This patch causes ACPI to fail upon VM boot
    #echo "Revert commit 'ACPI: add in a bad_madt_entry() function to eventually replace the macro'"
    #git revert 7494b07ebaae2117629024369365f7be7adc16c3 --no-edit

    #
    # Try apply patches under ~/
    #
    # dbgprint 1 "*************************"
    # for patchfile in `ls ~/*.patch`; do
    #     patch -f -p1 < $patchfile

    #     if [ $? != 0 ]; then
    #         dbgprint 0 "Failed to apply a patch."
    #         dbgprint 0 "Aborting the test."
    #         exit 20
    #     fi
    # done

    proc_count=$(cat /proc/cpuinfo | grep --count processor)

    dbgprint 1 "*************************"
    dbgprint 1 "Building the kernel."

    if [ $proc_count -eq 1 ]; then
        (time sudo make) >~/Perf_BuildKernel_make.log 2>&1
    else
        (time sudo make -j $proc_count) >~/Perf_BuildKernel_make.log 2>&1
    fi
}

#
# Write some useful info to the log file
#
dbgprint 1 "buildKernel.sh - Script to automate building of the kernel"
dbgprint 3 ""
dbgprint 3 "Global values"
dbgprint 3 "  DEBUG_LEVEL = ${DEBUG_LEVEL}"
dbgprint 3 "  SOURCE_TYPE = ${SOURCE_TYPE}"
dbgprint 3 "  LINUX_KERNEL_LOCATION = ${LINUX_KERNEL_LOCATION}"
dbgprint 3 "  TARBALL = ${TARBALL}"
dbgprint 3 "  KERNEL_VERSION = ${KERNEL_VERSION}"
dbgprint 3 "  CONFIG_FILE = ${CONFIG_FILE}"
dbgprint 3 ""

cd /mnt
if [ "${SOURCE_TYPE}" == "TARBALL" ]; then
    dbgprint 1 "Building linux kernel from tarball..."
    #
    # Make sure we were given the $TARBALL file
    #
    if [ ! ${TARBALL} ]; then
        dbgprint 0 "The TARBALL variable is not defined."
        dbgprint 0 "Aborting the test."
        exit 20
    fi

    dbgprint 3 "Extracting Linux kernel sources from ${TARBALL}"
    tar -jxvf ${TARBALL}
    sts=$?
    if [ 0 -ne ${sts} ]; then
        dbgprint 0 "tar failed to extract the kernel from the tarball: ${sts}"
        dbgprint 0 "Aborting test."
        exit 40
    fi

    #
    # The Linux Kernel is extracted to the folder which is named by the version by default
    #
    if [ ! -e ${KERNEL_VERSION} ]; then
        dbgprint 0 "The tar file did not create the directory: ${KERNEL_VERSION}"
        dbgprint 0 "Aborting the test."
        exit 50
    fi

    cd ${KERNEL_VERSION}
else
    dbgprint 1 "Building linux-next kernel from git repository..."
    #
    # Make sure we were given the linux-next git location
    #
    if [ ! ${LINUX_KERNEL_LOCATION} ]; then
        dbgprint 0 "The LINUX_KERNEL_LOCATION variable is not defined."
        dbgprint 0 "Aborting the test."
        exit 20
    fi

    if [ -e ${KERNEL_VERSION} ]; then
        cd ${KERNEL_VERSION}
        if [ "false" != "${FETCH_LATEST}" ]; then
            dbgprint 1 "Fetching latest sources."
            git fetch origin
            git reset --hard origin/master
        fi
    else
        sudo git clone --depth=7 ${LINUX_KERNEL_LOCATION}
        cd ${KERNEL_VERSION}
    fi
fi

#
if is_fedora ; then
    sudo yum install openssl-devel bc nfs-utils -y
    if [ $? -ne 0 ]; then
        LogMsg "Error: Unable to install required packages. Kernel compilation might fail."
    fi
elif is_ubuntu ; then
    sudo apt-get -y install nfs-common libssl-dev bc
    if [ $? -ne 0 ]; then
        LogMsg "ERROR: Unable to install libssl-devel. Aborting..."
    fi
elif is_suse ; then
    #If distro is SLES we need to install some packages first
    echo "Nothing to do."
fi

#
# Start the testing
#
echo "KernelRelease=${LINUX_VERSION}"
echo "$(uname -a)"

cp /boot/config-${LINUX_VERSION} .config

#
# Apply patches and build the new kernel
#
ApplyPatchesAndCompile
sts=$?
if [ 0 -ne ${sts} ]; then
    dbgprint 1 "Kernel make failed: ${sts}"

    retrycommit=~/${KERNEL_VERSION}_good.commit
    if [ -f $retrycommit ]; then
        dbgprint 1 "Trying again with last good build at commit $(cat $retrycommit)"
        git reset --hard $(cat $retrycommit)
        ApplyPatchesAndCompile
        sts=$?
    fi

    if [ 0 -ne ${sts} ]; then
        dbgprint 1 "Aborting test."
        echo "make: Failed"
        exit 110
    fi
fi
echo "make: Success"

#
# Install the kernel modules
#
dbgprint 1 "Building the kernel modules."
if [ $proc_count -eq 1 ]; then
    (time sudo make modules_install) >~/Perf_BuildKernel_makemodulesinstall.log 2>&1
else
    (time sudo make modules_install -j $proc_count) >~/Perf_BuildKernel_makemodulesinstall.log 2>&1
fi

sts=$?
if [ 0 -ne ${sts} ]; then
    dbgprint 1 "Kernel make failed: ${sts}"
    dbgprint 1 "Aborting test."
    echo "make modules_install: Failed"
    exit 110
else
    echo "make modules_install: Success"
fi

#
# Install the kernel
#
dbgprint 1 "Installing the kernel."
if [ $proc_count -eq 1 ]; then
    (time sudo make install) >~/Perf_BuildKernel_makeinstall.log 2>&1
else
    (time sudo make install -j $proc_count) >~/Perf_BuildKernel_makeinstall.log 2>&1
fi

sts=$?
if [ 0 -ne ${sts} ]; then
    echo "kernel build failed: ${sts}"
    echo "make install: Failed"
    exit 130
else
    echo "make install: Success"
fi

#
# Save the current Kernel version for comparision with the version
# of the new kernel after the reboot.
#
cd ~
dbgprint 3 "Saving version number of current kernel in oldKernelVersion.txt"
uname -r > ~/oldKernelVersion.txt

# Grub modification
grubversion=1
if [ -e /boot/grub/grub.conf ]; then
        grubfile="/boot/grub/grub.conf"
elif [ -e /boot/grub/menu.lst ]; then
        grubfile="/boot/grub/menu.lst"
elif [ -e /boot/grub2/grub.cfg ]; then
        grubversion=2
        grub2-mkconfig -o /boot/grub2/grub.cfg
        grub2-set-default 0
else
        echo "grub v1 files does not appear to be installed on this system. it should use grub v2."
        # the new kernel is the default one to boot next time
        grubversion=2
fi

if [ 1 -eq ${grubversion} ]; then
    echo "Update grub v1 files."
    new_default_entry_num="0"
    # added
    sudo sed --in-place=.bak -e "s/^default\([[:space:]]\+\|=\)[[:digit:]]\+/default\1$new_default_entry_num/" $grubfile
    # Display grub configuration after our change
    echo "Here are the new contents of the grub configuration file:"
    cat $grubfile
fi

# Remove the patch files
sudo rm -f ~/*.patch

if [ "true" = "${OVERWRITE_DEFAULT_KERNEL}" ]; then
    # Remove current kernel
    dbgprint 3 "Removing default kernel ${LINUX_VERSION}"
    sudo rm /boot/*${LINUX_VERSION}*
    sudo rm -rf /lib/modules/${LINUX_VERSION}
fi

#
# Let the caller know everything worked
#
dbgprint 1 "Exiting with state: TestCompleted."
exit 0
