use strict;
use warnings;
use POSIX qw(strftime);

my $vmid  = shift // '';
my $phase = shift // '';

my $HOSTPCI  = "hostpci0";
my $QM       = $ENV{GPU_ALLOCATE_QM}       // "/usr/sbin/qm";
my $CONF_DIR = $ENV{GPU_ALLOCATE_CONF_DIR} // "/etc/pve/qemu-server";
my $LOG      = $ENV{GPU_ALLOCATE_LOG}      // "/var/log/gpu-allocate.log";
my $REPRIME  = $ENV{GPU_ALLOCATE_REPRIME}  // "/var/lib/vz/snippets/gpu-reprime.sh";
my $FLAG_DIR = $ENV{GPU_ALLOCATE_FLAG_DIR} // "/run";

sub logmsg {
    my ($msg) = @_;
    my $ts = strftime("%Y-%m-%d %H:%M:%S", localtime);
    if (open(my $fh, ">>", $LOG)) { print $fh "[$ts] vm=$vmid phase=$phase $msg\n"; close($fh); }
    print "gpu-allocate: $msg\n";
}
sub slurp_file { my ($f)=@_; open(my $h,"<",$f) or return ''; local $/; my $c=<$h>//''; close($h); return $c; }
sub spit  { my ($f,$v)=@_; if (open(my $h,">",$f)){ print $h $v; close($h); } }

# The starting VM holds its config lock, so `qm config` on it would deadlock: read
# the file and drop the snapshot and pending sections. A peer goes through `qm
# config`, which resolves pending and prints no sections.
sub own_conf  { my $c = slurp_file("$CONF_DIR/${vmid}.conf"); $c =~ s/^\[.*\z//ms; return $c; }
sub peer_conf { my ($id)=@_; return `$QM config $id 2>/dev/null` // ''; }
sub holds_gpu { my ($id)=@_; my $c = $id eq $vmid ? own_conf() : peer_conf($id); return $c =~ /^\Q$HOSTPCI\E:/m ? 1 : 0; }
sub is_up     { my ($id)=@_; my $s = `$QM status $id 2>/dev/null` // ''; return $s =~ /\b(running|paused|suspended|prelaunch)\b/ ? 1 : 0; }

# An appended line lands in a [PENDING] or snapshot block and the VM boots without
# the card, so the line goes into the main section.
sub assign_gpu {
    my ($line) = @_;
    my $conf = "$CONF_DIR/${vmid}.conf";
    my $tmp  = "$conf.tmp.$$";
    my $c = slurp_file($conf);
    my ($main, $sections) = $c =~ /\A(.*?)(^\[.*)\z/ms ? ($1, $2) : ($c, '');
    $main =~ s/^\Q$HOSTPCI\E:.*\n//mg;

    my $ok = 0;
    if (open(my $fh, ">", $tmp)) {
        $ok = print $fh $main . "$line\n" . $sections;
        $ok &&= close($fh);
        $ok &&= rename($tmp, $conf);
    }
    unlink($tmp) unless $ok;
    return $ok;
}

my %GPU_VM = map { $_ => 1 } @GPU_VMS;
exit 0 unless $GPU_VM{$vmid};
my $flag = "$FLAG_DIR/gpu-reprime-$vmid";

if ($phase eq 'pre-start') {
    my @peers = sort grep { $_ ne $vmid } keys %GPU_VM;
    my %holds = map { ($_ => holds_gpu($_)) } sort keys %GPU_VM;

    for my $peer (@peers) {
        next unless is_up($peer);
        logmsg("ABORT: VM $peer is up and holds the GPU; shut it down first.");
        exit 1;
    }

    # The hostpci0 line is the record of the last holder: it survives a host reboot.
    my @holders = grep { $holds{$_} } sort keys %GPU_VM;
    my ($other) = grep { $_ ne $vmid } @holders;
    my $last = defined $other ? $other
             : (grep { $_ eq $vmid } @holders) ? $vmid
             : '';

    for my $peer (@peers) {
        next unless $holds{$peer};
        system("$QM set $peer --delete $HOSTPCI >/dev/null 2>&1");
        logmsg("released $HOSTPCI from VM $peer");
    }

    if (!assign_gpu("$HOSTPCI: $GPU_HOSTPCI")) {
        logmsg("ABORT: could not write $HOSTPCI into $CONF_DIR/${vmid}.conf");
        exit 1;
    }
    logmsg("assigned GPU to VM $vmid");

    # Proxmox read this VM's config before the hook ran, so a card that came from
    # another VM reaches QEMU only on the next full start: post-start schedules one.
    unlink($flag);
    if ($last eq '' || $last eq $vmid) {
        logmsg("same-VM boot (last='$last'); no reprime needed");
    } else {
        spit($flag, "1");
        logmsg("cross-VM switch (last=$last); will auto-reprime after start");
    }
    exit 0;
}

if ($phase eq 'post-start') {
    if (-e $flag) {
        unlink($flag);
        my $unit = "gpu-reprime-${vmid}-" . time();
        system("systemd-run --quiet --collect --unit=$unit $REPRIME $vmid");
        logmsg("scheduled auto-reprime (full stop+start) as $unit");
    }
    exit 0;
}

exit 0;
