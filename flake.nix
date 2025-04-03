# packageing heavily inspired (copied) from https://pyproject-nix.github.io/uv2nix/usage/hello-world.html

{
  description = "Hello world flake using uv2nix";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      uv2nix,
      pyproject-nix,
      pyproject-build-systems,
      ...
    }:
    let
      inherit (nixpkgs) lib;
    in
    {
      packages = builtins.mapAttrs (
        system: _:
        let
          workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

          # Create package overlay from workspace.
          overlay = workspace.mkPyprojectOverlay {
            # Prefer prebuilt binary wheels as a package source.
            # Sdists are less likely to "just work" because of the metadata missing from uv.lock.
            # Binary wheels are more likely to, but may still require overrides for library dependencies.
            sourcePreference = "wheel"; # or sourcePreference = "sdist";
            # Optionally customise PEP 508 environment
            # environ = {
            #   platform_release = "5.10.65";
            # };

          };

          # Extend generated overlay with build fixups
          #
          # Uv2nix can only work with what it has, and uv.lock is missing essential metadata to perform some builds.
          # This is an additional overlay implementing build fixups.
          # See:
          # - https://pyproject-nix.github.io/uv2nix/FAQ.html
          pyprojectOverrides = _final: _prev: {
            # Implement build fixups here.
            # Note that uv2nix is _not_ using Nixpkgs buildPythonPackage.
            # It's using https://pyproject-nix.github.io/pyproject.nix/build.html

            # varint failed with missing setuptools. so it's added manually
            varint = _prev.varint.overrideAttrs (old: {
              nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [
                _final.setuptools # Add setuptools to build environment
              ];
            });

          };

          pkgs = nixpkgs.legacyPackages.${system};

          # Use Python 3.12 from nixpkgs
          python = pkgs.python312;

          # Construct package set
          pythonSet =
            # Use base package set from pyproject.nix builders
            (pkgs.callPackage pyproject-nix.build.packages {
              inherit python;
            }).overrideScope
              (
                lib.composeManyExtensions [
                  pyproject-build-systems.overlays.default
                  overlay
                  pyprojectOverrides
                ]
              );
        in
        {
          default = pythonSet.mkVirtualEnv "immich-upload-daemon-env" workspace.deps.default;
        }
      ) nixpkgs.legacyPackages;

      # Make immich_upload_daemon runnable with `nix run`
      apps = builtins.mapAttrs (system: _: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/immich_upload_daemon";
        };
      }) nixpkgs.legacyPackages;

      homeManagerModules.default =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        let
          cfg = config.services.immich-upload;
        in
        {
          options.services.immich-upload = with lib.types; {
            enable = lib.mkEnableOption "Immich-Upload-Daemon";
            baseUrl = lib.mkOption {
              type = uniq str;
              description = ''
                URL of your Immich server
              '';
            };
            apiKey = lib.mkOption {
              type = uniq str;
              description = ''
                Your API KEY. you can generate one in you Immich user settings
              '';
            };
            mediaPaths = lib.mkOption {
              type = listOf str;
              default = [ ];
              description = ''
                Directories to upload
                example: [ "~/Pictures" "~/Videos" ]
              '';
            };
            chunkSize = lib.mkOption {
              type = uniq ints.positive;
              default = 65536;
              description = ''
                Reading chunk size, increase to improve speed at cost of memory. 
              '';
            };
            wifiOnly = lib.mkOption {
              type = bool;
              default = false;
              description = ''
                Set to true if uploads should occur only over WiF
              '';
            };
            ssid = lib.mkOption {
              type = uniq str;
              default = "";
              description = ''
                Specific WiFi network name to check when WIFI_ONLY is enabled.
              '';
            };
            notMetered = lib.mkOption {
              type = bool;
              default = false;
              description = ''
                Set to true to upload only on non-metered networks
              '';
            };
            logLevel = lib.mkOption {
              type = enum [
                "debug"
                "normal"
              ];
              default = "normal";
              description = ''
                Enable debugging logs when set to "debug"
              '';
            };
          };
          config = lib.mkIf cfg.enable {
            home.file."${config.xdg.configHome}/immich_upload_daemon/immich_upload_daemon.env" = {
              force = true;
              text = ''
                BASE_URL="${cfg.baseUrl}"
                API_KEY="${cfg.apiKey}"
                MEDIA_PATHS="${builtins.concatStringsSep "," cfg.mediaPaths}"
                CHUNK_SIZE=${builtins.toString cfg.chunkSize}
                WIFI_ONLY=${if cfg.wifiOnly then "True" else "False"}
                SSID="${cfg.ssid}"
                NOT_METERED=${if cfg.notMetered then "True" else "False"}
                DEBUG=${if cfg.logLevel == "debug" then "True" else "False"}
              '';
            };
            systemd.user.services.immich-upload-daemon = {
              Install.WantedBy = [ "default.target" ];
              Unit.After = [ "network.target" ];
              Unit.Description = "Immich Upload Daemon";
              Service.ExecStart = "${self.packages.${pkgs.system}.default}/bin/immich_upload_daemon";
            };
          };
        };
    };
}
