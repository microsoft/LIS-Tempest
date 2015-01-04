# Set static IP $1 on interface $3
# It's up to the caller to make sure the interface is shut down in case this function fails
# Parameters:
# $1 == static ip
# $2 == netmask
# $3 == interface

sudo su

LogMsg()
{
	echo $(date "+%a %b %d %T %Y") : "${1}" >> ~/$0.log
}

if [ 2 -gt $# ]; then
	LogMsg "SetIPstatic accepts 3 arguments: 1. static IP, 2. network interface, 3. (optional) netmask"
	exit 100
fi

if [ 0 -ne $? ]; then
	LogMsg "Parameter $1 is not a valid IPv4 Address"
	exit 1
fi

ip link show "$3" > /dev/null 2>&1
if [ 0 -ne $? ]; then
	LogMsg "Network adapter $3 is not working."
	exit 2
fi

declare __netmask
declare __interface
declare __ip

__netmask="$2"
__interface="$3"
__ip="$1"

if [ "$__netmask" -ge 32 -o "$__netmask" -le 0 ]; then
	LogMsg "SetIPstatic: $__netmask is not a valid cidr netmask"
	exit 4
fi

LogMsg "Setting up static ip for dev $__interface"
ip link set "$__interface" down
ip addr flush "$__interface"
ip addr add "$__ip"/"$__netmask" dev "$__interface"
ip link set "$__interface" up

if [ 0 -ne $? ]; then
	LogMsg "Unable to assign address $__ip/$__netmask to $__interface."
	exit 5
fi

# Get IP-Address
declare __IP_ADDRESS
__IP_ADDRESS=$(ip -o addr show "${__interface}" | grep -vi inet6 | cut -d '/' -f1 | awk '{print $NF}' | grep -vi '[a-z]')

if [ -z "$__IP_ADDRESS" ]; then
	LogMsg "IP address $__ip did not get assigned to $__interface"
	exit 3
fi

# Check that addresses match
if [ "$__IP_ADDRESS" != "$__ip" ]; then
	LogMsg "New address $__IP_ADDRESS differs from static ip $__ip on interface $__interface"
	exit 6
fi
# OK
exit 0