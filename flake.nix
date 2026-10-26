{
  description = "Corsair development tools for macOS and Linux";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { nixpkgs, ... }:
    let
      systems = [ "aarch64-darwin" "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let pkgs = import nixpkgs { inherit system; config = {}; overlays = []; };
        in {
          default = pkgs.mkShellNoCC ({
            packages = with pkgs; [ python312 uv just bashInteractive docker-client temporal-cli ];
            # uv reads the committed .python-version (3.12) in and out of this shell; preferring
            # system interpreters picks this python312, first on PATH, for a new .venv, and keeps a
            # 3.12 .venv built outside the shell instead of silently recreating it without extras.
            UV_PYTHON_PREFERENCE = "system";
            UV_PYTHON_DOWNLOADS = "never";
          } // pkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
            LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.zlib ];
          });
        });
    };
}
