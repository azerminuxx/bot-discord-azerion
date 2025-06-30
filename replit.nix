{ pkgs }: {
  deps = [
    pkgs.python310
    pkgs.python310Packages.pillow
    pkgs.python310Packages.pip
  ];
}
