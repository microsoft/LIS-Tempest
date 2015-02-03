# Setup a bridge named br0
# $1 == Bridge IP Address
# $2 == Bridge netmask
# $3 - $# == Interfaces to attach to bridge
# if no parameter is given outside of IP and Netmask, all interfaces will
# be added (except lo)
echoerr() { echo "$@" 1>&2; }
sudo man brctl > /dev/null
if [ "$?" != "0" ]; then
	. utils.sh
	installBridgeUtils
fi

LogMsg()
{
	echo $(date "+%a %b %d %T %Y"): "${1}"
}

if [ $# -lt 2 ]; then
    LogMsg "SetupBridge needs at least 2 parameters"
    exit 1
fi

declare -a __bridge_interfaces
declare __bridge_ip
declare __bridge_netmask

__bridge_ip="$1"
__bridge_netmask="$2"


if [ "$__bridge_netmask" -ge 32 -o "$__bridge_netmask" -le 0 ]; then
	echoerr "SetupBridge: $__bridge_netmask is not a valid cidr netmask"
	exit 4
fi

# get rid of the first two parameters
shift
shift
# and loop through the remaining ones
declare __iterator
for __iterator in "$@"; do
	sudo ip link show "$__iterator" >/dev/null 2>&1
	if [ 0 -ne $? ]; then
		echoerr "SetupBridge: Interface $__iterator not working or not present"
		exit 4
	fi
	__bridge_interfaces=("${__bridge_interfaces[@]}" "$__iterator")
done

# create bridge br0
sudo brctl addbr br0
if [ 0 -ne $? ]; then
	echoerr "SetupBridge: unable to create bridge br0"
	exit 5
fi

# turn off stp
sudo brctl stp br0 off

declare __iface
# set all interfaces to 0.0.0.0 and then add them to the bridge
for __iface in ${__bridge_interfaces[@]}; do
	sudo ip link set "$__iface" down
	sudo ip addr flush dev "$__iface"
	sudo ip link set "$__iface" up
	sudo ip link set dev "$__iface" promisc on
	#add interface to bridge
	sudo brctl addif br0 "$__iface"
	if [ 0 -ne $? ]; then
		echoerr "SetupBridge: unable to add interface $__iface to bridge br0"
		exit 6
	fi
	echo "SetupBridge: Added $__iface to bridge"
	sudo echo "1" > sudo /proc/sys/net/ipv4/conf/"$__iface"/proxy_arp
	sudo echo "1" > sudo /proc/sys/net/ipv4/conf/"$__iface"/forwarding

done

#setup forwarding on bridge
sudo echo "1" > sudo /proc/sys/net/ipv4/conf/br0/forwarding
sudo echo "1" > sudo /proc/sys/net/ipv4/conf/br0/proxy_arp
sudo echo "1" > sudo /proc/sys/net/ipv4/ip_forward
sudo iptables -D FORWARD 1
sudo ip link set br0 down
sudo ip addr add "$__bridge_ip"/"$__bridge_netmask" dev br0
sudo ip link set br0 up
echo "$(brctl show br0)"
echo "SetupBridge: Successfull"
# done
exit 0
