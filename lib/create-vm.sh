pw=$(read_secret "$sudo_ref")
node() { printf '%s\n' "$pw" | ssh -o ConnectTimeout=10 "$node_ssh" "sudo -S -p '' bash -c $(printf %q "$1")"; }

storage=${rootfs%%:*}
size=${rootfs##*:}
staged=$staging/$image

if node "qm status $vmid" >/dev/null 2>&1; then
  node "qm config $vmid" | grep -qx "name: $host" \
    || { echo "vmid $vmid on $node_ssh is not $host" >&2; exit 1; }
else
  node "install -d -m 0700 $staging; test -f /tmp/$image && mv /tmp/$image $staged; test -f $staged" \
    || { echo "no $image on $node_ssh: nix run .#vm-image" >&2; exit 1; }
  node "qm create $vmid --name $host --machine q35 --bios ovmf --ostype l26 --cpu host --onboot 0 \
    --cores $cores --memory $memory --balloon 0 --scsihw virtio-scsi-single --serial0 socket --agent 1 \
    --efidisk0 $storage:0,efitype=4m,pre-enrolled-keys=0 \
    --net0 virtio=$hwaddr,bridge=vmbr0,firewall=1 --description $(printf %q "$description")"
  node "qm set $vmid --scsi0 $storage:0,import-from=$staged"
  node "rm -f $staged"
  node "qm resize $vmid scsi0 ${size}G"
  slot=1
  for disk in "${extra_disks[@]}"; do
    node "qm set $vmid --scsi$slot $disk"
    slot=$((slot + 1))
  done
  node "qm set $vmid --boot order=scsi0"
fi

[[ $(node "qm status $vmid") == *running* ]] || node "qm start $vmid"
address=
for _ in $(seq 60); do
  address=$(node "qm guest cmd $vmid network-get-interfaces" 2>/dev/null |
    jq -r '.. | objects | select(."ip-address-type" == "ipv4") | ."ip-address"' |
    grep -v '^127\.' | awk 'NR == 1') || true
  [ -z "$address" ] || break
  sleep 5
done
[ -n "$address" ] || { echo "vm $vmid has no address: the guest agent or dhcp never answered" >&2; exit 1; }
echo "VM $vmid up at $address, next: nix run .#switch-$host -- root@$address"
