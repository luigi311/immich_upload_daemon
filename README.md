# Immich Upload Daemon

Immich Upload Daemon is a tool designed to monitor your media directories for new image and video files and automatically upload them to an Immich server. It leverages efficient file scanning, an SQLite database for tracking, and network condition checks to ensure uploads occur only under optimal conditions.

## Features

- **Media File Monitoring**  
  Uses file system watchers to detect new media files (with popular image and video extensions) in your specified directories.

- **Asynchronous Operations**  
  Built using Python’s `asyncio` to concurrently scan directories, update the database, and manage network operations.

- **Database Management**  
  Maintains a database of media files to track uploads, preventing duplicate processing.

- **Network-Aware Uploading**  
  Checks for WiFi-only or non-metered connections before uploading to reduce unnecessary data usage.

- **Configurable Environment**  
  Easily configure your Immich server details, media paths, and network requirements via an environment file.

## Configuration

Before running the daemon, configure your environment settings:

1. **Environment File**  
   The daemon expects an environment file at:
   ```
   ~/.config/immich_upload_daemon/immich_upload_daemon.env
   ```
   If this file doesn’t exist, a default one is generated. Edit the file to set the following variables:

   - **BASE_URL**: Base URL of your Immich server.
   - **API_KEY**: Your Immich API key.
   - **MEDIA_PATHS**: Comma-separated directories to monitor (e.g., `~/Pictures, ~/Videos`).
   - **CHUNK_SIZE**: Reading chunk size, increase to improve speed at cost of memory. Default 65536
   - **WIFI_ONLY**: Set to `true` if uploads should occur only over WiFi.
   - **SSID**: (Optional) Specific WiFi network name to check when WIFI_ONLY is enabled.
   - **NOT_METERED**: Set to `true` to upload only on non-metered networks.
   - **DEBUG**: Enable debugging logs when set to `true`.

   Adjust these values according to your setup.

## Running the Daemon

Once installed, run the daemon by starting the service:
```sh
systemctl --user enable immich_upload_daemon
systemctl --user start immich_upload_daemon
```

or manually running the binary
```sh
immich_upload_daemon
```

## Installation

### Packaged

For users who prefer a prebuilt binary, .deb packages are provided via GitHub Releases.

1. **Download the .deb Package**  
   Navigate to the [GitHub Releases page](https://github.com/luigi311/immich_upload_daemon/releases) and download the appropriate package for your system architecture (e.g., `immich_upload_daemon-x86_64.deb` or `immich_upload_daemon-arm64.deb`).

2. **Install the Package**  
   Once downloaded, install the package using your package manager. For example, on Debian-based systems:
   ```sh
   sudo dpkg -i ./immich_upload_daemon-*.deb
   ```
   If any dependency errors occur, run:
   ```sh
   sudo apt-get install -f
   ```

3. **Manage the Service**  
   The package installs a systemd service file. Enable and start the daemon using:
   ```sh
   systemctl --user enable immich_upload_daemon
   systemctl --user start immich_upload_daemon
   ```
   To check the status, run:
   ```sh
   systemctl --user status immich_upload_daemon
   ```

### From Source

This project uses [uv](https://github.com/astral-sh/uv) for dependency management and building. Follow these steps to install and build the daemon from source:

1. **Install uv**  
   Follow the official installation instructions for [uv](https://github.com/astral-sh/uv).

2. **Synchronize Dependencies**  
   Run the following command to synchronize your project’s dependencies with a frozen lockfile:
   ```sh
   uv sync --frozen
   ```

3. **Build the Project**  
   Build the project using:
   ```sh
   uv build
   ```

4. **Create the Executable**  
   Use `uvx` to generate a self-contained executable (PEX file). For example:
   ```sh
   uvx --python .venv/bin/python pex \
       dist/immich_upload_daemon-*.whl \
       -e immich_upload_daemon.main:main \
       -o dist/immich_upload_daemon.pex \
       --python-shebang '#!/usr/bin/env python3' \
       --scie eager \
       --scie-pbs-stripped
   ```

5. **(Optional) Build a Debian Package**  
   A GitHub workflow is provided to automatically package the daemon. To build manually after generating the executable, run:
   ```sh
   VERSION=$(grep -E '^version\s*=' pyproject.toml | head -n1 | sed -E 's/version\s*=\s*"(.*)"/\1/')
   fpm -s dir -t deb \
       -n immich-upload-daemon \
       -v "$VERSION" \
       --deb-systemd systemd/immich_upload_daemon.service \
       --deb-systemd-path /usr/lib/systemd/user \
       dist/immich_upload_daemon=/usr/bin/immich_upload_daemon
       
   ```

6. **Install the Service File**  
   Copy the `immich_upload_daemon.service` file to your systemd user directory (typically `~/.config/systemd/user/` or `/usr/lib/systemd/user/`).


### Using Nix

#### Run the application once

>environment file has to be present

`nix run github:luigi311/immich_upload_daemon`

#### Install and configure with Homemanager

This flake outputs a homeManagerModule. It can be imported in a HomeManager Config. The following config configures the systemd service as well as the environment file:

```nix
services.immich-upload = {
   enable = true;
   baseUrl = "https://photos.example.com/api";
   apiKey = secrets.immich.apiKey;
   mediaPaths = [ 
      "~/Pictures"
      "~/Videos"
   ];

   # optional:
   wifiOnly = true;
   ssid = "veryCoolWifiName";
   logLevel = "debug";
   notMetered = true;
   chunkSize = 65536;
};
```

## Development

Developers are welcome to contribute. Below are some guidelines:

- **Project Structure**  
  - `src/immich_upload_daemon/`: Main package containing modules for file handling, database operations, network checks, and the main application loop.
  - `pyproject.toml`: Project metadata and dependency definitions.
  - `.github/workflows/`: CI/CD configuration for building and packaging the daemon.

- **Asynchronous Code**  
  The project extensively uses Python’s asynchronous programming. When adding features or fixes, ensure non-blocking code practices are maintained.

- **Contribution Guidelines**  
  Open issues or pull requests with clear descriptions and commit messages. Follow the established coding style for consistency.
