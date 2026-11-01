pw=$(read_secret "$sudo_ref")
node() { printf '%s\n' "$pw" | ssh -o ConnectTimeout=10 "$node_ssh" "sudo -S -p '' bash -c $(printf %q "$1")"; }

if ! node "pct status $vmid" >/dev/null 2>&1; then
  node "test -f /tmp/$template && mv /tmp/$template /var/lib/vz/template/cache/; test -f /var/lib/vz/template/cache/$template" \
    || { echo "no $template on $node_ssh: nix run .#template" >&2; exit 1; }
  node "pct create $vmid local:vztmpl/$template --ostype unmanaged --hostname $host --unprivileged 1 --features nesting=1 --cmode console --onboot 1 \
    --cores $cores --memory $memory --swap $swap --rootfs $rootfs --net0 name=eth0,bridge=vmbr0,firewall=1,hwaddr=$hwaddr,ip=dhcp --description $(printf %q "$description")"
  slot=0
  for mount in "${mounts[@]}"; do
    node "pct set $vmid --mp$slot $mount" >/dev/null
    slot=$((slot + 1))
  done
fi
node "pct set $vmid --dev0 /dev/net/tun,mode=0666" >/dev/null
slot=1
for device in "${devices[@]}"; do
  node "pct set $vmid --dev$slot $device" >/dev/null
  slot=$((slot + 1))
done
[[ $(node "pct status $vmid") == *running* ]] || { node "pct start $vmid"; sleep 5; }
address=$(node "pct exec $vmid -- /run/current-system/sw/bin/ip -4 -o addr show eth0" | awk '{print $4}' | cut -d/ -f1)
echo "CT $vmid up at $address, next: nix run .#switch-$host -- root@$address"
