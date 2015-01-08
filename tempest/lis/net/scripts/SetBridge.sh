# Setup a bridge named br0
# $1 == Bridge IP Address
# $2 == Bridge netmask
# $3 - $# == Interfaces to attach to bridge
# if no parameter is given outside of IP and Netmask, all interfaces will be added (except lo)

sudo su

LogMsg()
{
	echo $(date "+%a %b %d %T %Y") : "${1}"  >> ~/$0.log
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
	LogMsg "SetupBridge: $__bridge_netmask is not a valid cidr netmask"
	exit 4
fi

# get rid of the first two parameters
shift
shift
# and loop through the remaining ones
declare __iterator
for __iterator in "$@"; do
	ip link show "$__iterator" >/dev/null 2>&1
	if [ 0 -ne $? ]; then
		LogMsg "SetupBridge: Interface $__iterator not working or not present"
		exit 4
	fi
	__bridge_interfaces=("${__bridge_interfaces[@]}" "$__iterator")
done

# create bridge br0
brctl addbr br0
if [ 0 -ne $? ]; then
	LogMsg "SetupBridge: unable to create bridge br0"
	exit 5
fi

# turn off stp
brctl stp br0 off

declare __iface
# set all interfaces to 0.0.0.0 and then add them to the bridge
for __iface in ${__bridge_interfaces[@]}; do
	ip link set "$__iface" down
	ip addr flush dev "$__iface"
	ip link set "$__iface" up
	ip link set dev "$__iface" promisc on
	#add interface to bridge
	brctl addif br0 "$__iface"
	if [ 0 -ne $? ]; then
		LogMsg "SetupBridge: unable to add interface $__iface to bridge br0"
		exit 6
	fi
	LogMsg "SetupBridge: Added $__iface to bridge"
	echo "1" > /proc/sys/net/ipv4/conf/"$__iface"/proxy_arp
	echo "1" > /proc/sys/net/ipv4/conf/"$__iface"/forwarding

done

#setup forwarding on bridge
echo "1" > /proc/sys/net/ipv4/conf/br0/forwarding
echo "1" > /proc/sys/net/ipv4/conf/br0/proxy_arp
echo "1" > /proc/sys/net/ipv4/ip_forward
 iptables -D FORWARD 1
ip link set br0 down
ip addr add "$__bridge_ip"/"$__bridge_netmask" dev br0
ip link set br0 up
LogMsg "$(brctl show br0)"
LogMsg "SetupBridge: Successfull"
# done
exit 0
