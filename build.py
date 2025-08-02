# build.py
import subprocess
import sys

def main():
    subprocess.check_call([
        sys.executable,
        "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--output-filename=immich_upload_daemon",
        "--enable-plugin=implicit-imports",
        "--remove-output",
        "src/immich_upload_daemon/main.py",
    ])

if __name__ == "__main__":
    main()
