let
  script = pkgs: name: runtimeInputs: text: pkgs.writeShellApplication {
    inherit name runtimeInputs text;
    excludeShellChecks = [ "SC2029" ];
  };

  defaultBootstrap = host: "hosts/${host}/bootstrap";
in
{
  testsIn = { pkgs, dir, args ? { } }:
    pkgs.lib.concatMapAttrs (name: _:
      let
        p = dir + "/${name}/tests";
        tests = import p;
      in pkgs.lib.optionalAttrs (builtins.pathExists (p + "/default.nix"))
        (pkgs.lib.mapAttrs' (test: pkgs.lib.nameValuePair "${name}-${test}")
          (tests (builtins.intersectAttrs (builtins.functionArgs tests) ({ inherit pkgs; } // args))))
    ) (builtins.readDir dir);

  darwinScripts = { self, pkgs, bootstrap ? defaultBootstrap }:
    pkgs.lib.concatMapAttrs (host: _: {
      "check-${host}" = script pkgs "check-${host}" [ ] "nix eval --raw .#darwinConfigurations.${host}.system";
      "build-${host}" = script pkgs "build-${host}" [ ] "nix build --no-link --print-out-paths .#darwinConfigurations.${host}.system";
      # darwin-rebuild resets HOME to ~root, whose git cannot reach private
      # inputs: a lock bumped elsewhere would stop the switch on a GitHub
      # prompt. Built first as the user, every input is already in the store.
      "switch-${host}" = script pkgs "switch-${host}" [ ] ''
        nix build --no-link .#darwinConfigurations.${host}.system
        sudo /run/current-system/sw/bin/darwin-rebuild switch --flake .#${host} "$@"
      '';
      "bootstrap-${host}" = script pkgs "bootstrap-${host}" [ ] ''exec ${bootstrap host} "$@"'';
    }) (self.darwinConfigurations or { });

  estateScripts =
    { self
    , pkgs
    , builder
    , readSecret
    , renderSecret ? null
    , bootstrap ? defaultBootstrap
    , template ? "nixos-dnix.tar.xz"
    , vmImage ? "nixos-dnix.qcow2"
    , vmStaging ? "/var/lib/vz/dnix"
    , templateNode ? null
    , imageNode ? null
    }:
    let
      lib = pkgs.lib;
      node = name: self.systemConfigs.${name}.config.dnix.node;

      pushSecrets = host: secrets: preamble:
        let files = lib.mapAttrs (_: f: { inherit (f) template owner group mode path; }) secrets.files;
        in lib.optionalString (files != { }) (
          assert lib.assertMsg (renderSecret != null) "estateScripts: ${host} declares dnix.secrets.files, so pass renderSecret.";
          preamble + ''
            secrets_dir=${lib.escapeShellArg secrets.dir}
            secrets_json=${pkgs.writeText "${host}-secrets.json" (builtins.toJSON files)}
            render() { ${renderSecret}; }
          '' + builtins.readFile ./push-secrets.sh);

      remoteBuild = attr: ''
        drv=$(nix eval --raw .#${attr}.drvPath)
        nix-copy-closure --to ${builder} "$drv"
        out=$(ssh ${builder} "nix build --no-link --print-out-paths '$drv^*'")
      '';

      nixosScripts = lib.concatMapAttrs (host: cfg:
        let
          g = cfg.config.dnix.guest;
          n = node g.node;
          create = {
            lxc = ''
              template=${template}
              swap=${toString g.swap}
              devices=(${lib.concatMapStringsSep " " lib.escapeShellArg g.devices})
              mounts=(${lib.concatMapStringsSep " " lib.escapeShellArg g.mounts})
            '' + builtins.readFile ./create-lxc.sh;
            vm = ''
              image=${vmImage}
              staging=${vmStaging}
              extra_disks=(${lib.concatMapStringsSep " " lib.escapeShellArg g.extraDisks})
            '' + builtins.readFile ./create-vm.sh;
          };
        in {
        "check-${host}" = script pkgs "check-${host}" [ ] "nix eval --raw .#nixosConfigurations.${host}.config.system.build.toplevel.drvPath";
        "build-${host}" = script pkgs "build-${host}" [ ] (remoteBuild "nixosConfigurations.${host}.config.system.build.toplevel" + ''echo "$out"'');
        "switch-${host}" = script pkgs "switch-${host}" [ pkgs.nixos-rebuild pkgs.jq ] (''
          target="''${1:-root@${host}}"
        '' + pushSecrets host cfg.config.dnix.secrets ''
          ssh_target=$target
          remote() { ssh "$ssh_target" "$1"; }
        '' + ''
          nixos-rebuild switch --flake .#${host} --build-host ${builder} --target-host "$target"
        '');
        "bootstrap-${host}" = script pkgs "bootstrap-${host}" [ pkgs.jq ] (''
          read_secret() { ${readSecret} "$1"; }
          host=${host}
          node_ssh=${n.ssh}
          sudo_ref=${lib.escapeShellArg n.sudoPasswordRef}
          vmid=${toString g.vmid}
          cores=${toString g.cores}
          memory=${toString g.memory}
          rootfs=${lib.escapeShellArg g.rootfs}
          hwaddr=${lib.escapeShellArg g.hwaddr}
          description=${lib.escapeShellArg g.description}
        '' + create.${g.platform});
      }) (self.nixosConfigurations or { });

      systemScripts = lib.concatMapAttrs (host: cfg: let n = cfg.config.dnix.node; in {
        "check-${host}" = script pkgs "check-${host}" [ ] "nix eval --raw .#systemConfigs.${host}.drvPath";
        "build-${host}" = script pkgs "build-${host}" [ ] (remoteBuild "systemConfigs.${host}" + ''echo "$out"'');
        "switch-${host}" = script pkgs "switch-${host}" [ pkgs.jq ] (remoteBuild "systemConfigs.${host}" + ''
          nix copy --no-check-sigs --from ssh://${builder} --to 'ssh://${n.ssh}?remote-program=/nix/var/nix/profiles/default/bin/nix-store' "$out"
          pw=$(${readSecret} ${lib.escapeShellArg n.sudoPasswordRef})
          node() { printf '%s\n' "$pw" | ssh ${n.ssh} "sudo -S -p ''' bash -c $(printf %q "$1")"; }
        '' + pushSecrets host cfg.config.dnix.secrets ''
          ssh_target=${n.ssh}
          remote() { node "$1"; }
        '' + ''
          node "$out/bin/register-profile && $out/bin/activate"
          if ssh ${n.ssh} test -f /run/reboot-required; then echo "reboot required on ${n.ssh}"; fi
        '');
        "bootstrap-${host}" = script pkgs "bootstrap-${host}" [ ] ''exec ${bootstrap host} "$@"'';
      }) (self.systemConfigs or { });

      staging = lib.optionalAttrs (templateNode != null) {
        template = script pkgs "template" [ ] (remoteBuild "packages.x86_64-linux.lxc-template" + ''
          scp -3 "${builder}:$out/tarball/"*.tar.xz ${(node templateNode).ssh}:/tmp/${template}
          echo "staged ${(node templateNode).ssh}:/tmp/${template}"
        '');
      } // lib.optionalAttrs (imageNode != null) {
        vm-image = script pkgs "vm-image" [ ] (remoteBuild "packages.x86_64-linux.vm-image" + ''
          scp -3 "${builder}:$out/"*.qcow2 ${(node imageNode).ssh}:/tmp/${vmImage}
          echo "staged ${(node imageNode).ssh}:/tmp/${vmImage}"
        '');
      };
    in
    nixosScripts // systemScripts // staging;
}
