{ pkgs, ... }: {
  # Nix language channel
  channel = "stable-24.05";

  # Enable the Docker daemon service. This is required to run Docker containers.
  services.docker.enable = true;

  # Define the packages needed for the development environment.
  packages = [
    pkgs.docker-compose
    pkgs.docker
    pkgs.python3
    pkgs.python3Packages.pip
    pkgs.nodejs_20
  ];

  # Define recommended VS Code extensions.
  idx.extensions = [
    "ms-python.python"
    "ms-azuretools.vscode-docker"
    "dbaeumer.vscode-eslint"
  ];

  idx.previews = {
    enable = true;
  };

  # No specific workspace hooks needed for this setup
  idx.workspace = {
    onCreate = {};
    onStart = {};
  };
}