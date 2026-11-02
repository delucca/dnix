{ pkgs, vms, hostpci }:

let
  quoted = pkgs.lib.replaceStrings [ "\\" "'" ] [ "\\\\" "\\'" ] hostpci;
in
pkgs.writeTextFile {
  name = "gpu-allocate.pl";
  executable = true;
  text = ''
    #!/usr/bin/perl
    my @GPU_VMS = (${pkgs.lib.concatMapStringsSep ", " toString vms});
    my $GPU_HOSTPCI = '${quoted}';
  '' + builtins.readFile ./allocate.pl;
  checkPhase = "${pkgs.perl}/bin/perl -c $target";
}
