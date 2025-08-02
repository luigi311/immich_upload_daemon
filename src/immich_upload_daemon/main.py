import asyncio
import uvloop
import os
import signal
import sys

from aiofiles import open
from dotenv import dotenv_values
from loguru import logger
from watchdog.observers import Observer
from xdg.BaseDirectory import xdg_config_home

from immich_upload_daemon.immich import upload
from immich_upload_daemon.database import Database, get_db_path
from immich_upload_daemon.files import MediaFileHandler, scan_existing_files
from immich_upload_daemon.network import check_network_conditions
from immich_upload_daemon.utils import str_to_bool

# A global event to signal shutdown
shutdown_event = asyncio.Event()
new_file_event = asyncio.Event()


def shutdown():
    logger.info("Received shutdown signal, initiating graceful shutdown...")
    shutdown_event.set()


async def watcher(db: Database, queue: asyncio.Queue):
    """
    Asynchronous watcher that processes file paths from the queue.
    """
    while not shutdown_event.is_set():
        logger.info("Waiting for a new files...")

        # Wait for a new file path from the watchdog handler.
        file_path = await queue.get()

        if os.path.exists(file_path):
            if await db.add_media(file_path):
                new_file_event.set()

        queue.task_done()


async def uploader(
    db: Database,
    base_url: str,
    api_key: str,
    chunk_size: int,
    # Conditions
    wifi_only: bool,
    ssid: str | None,
    not_metered: bool,
):
    while not shutdown_event.is_set():
        # Wait for a new file event to upload
        await new_file_event.wait()

        while True:
            condition = await check_network_conditions(wifi_only, ssid, not_metered)
            if condition:
                break

            logger.warning("Rechecking network condition in 10 mins")
            await asyncio.sleep(60 * 10)

        unuploaded = await db.get_unuploaded()

        # Only clear when unuploaded comes back empty to prevent issues with
        # new files being discovered during the uploading process
        if not unuploaded:
            new_file_event.clear()
            logger.info("Waiting for a new files...")

        for file_name in unuploaded:
            try:
                if await upload(base_url, api_key, file_name, chunk_size):
                    await db.mark_uploaded(file_name)
            
            except FileNotFoundError:
                await db.remove_media(file_name)


async def create_default_config(env_file: str):
    # Create a default env file if it doesn't exist
    async with open(env_file, "w") as f:
        await f.write(
            """BASE_URL
API_KEY
MEDIA_PATHS
CHUNK_SIZE=65536
DEBUG=True

# Conditions
WIFI_ONLY=False
SSID
NOT_METERED=False
"""
        )


def configure_logger(debug: bool) -> None:
    # Remove default logger to configure our own
    logger.remove()

    level = "INFO"
    if debug:
        level = "DEBUG"

    logger.add(sys.stdout, level=level)


async def run():
    # Load environment variables
    env_file = os.path.join(
        xdg_config_home, "immich_upload_daemon", "immich_upload_daemon.env"
    )
    if not os.path.exists(env_file):
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(env_file), exist_ok=True)

        await create_default_config(env_file)

    env = dotenv_values(env_file)

    BASE_URL: str | None = env.get("BASE_URL")
    API_KEY: str | None = env.get("API_KEY")
    media_paths: str | None = env.get("MEDIA_PATHS")
    chunk_size: int | str | None = env.get("CHUNK_SIZE", 65536)
    wifi_only: bool = str_to_bool(env.get("WIFI_ONLY"))
    ssid: str | None = env.get("SSID")
    not_metered: bool = str_to_bool(env.get("NOT_METERED"))
    debug: bool = str_to_bool(env.get("DEBUG"))

    configure_logger(debug)

    if not BASE_URL or not API_KEY:
        logger.error(f"Please set BASE_URL and API_KEY in {env_file}")
        return

    # Default chunk_size
    # Fallback for if chunk_size key exists but not set
    if not chunk_size:
        chunk_size = 65536
    if isinstance(chunk_size, str):
        chunk_size = int(chunk_size)

    # Strip trailing slashes
    BASE_URL = BASE_URL.rstrip("/")

    db = Database(get_db_path("files.db"))
    await db.init_db()

    # Create an asyncio queue for file events.
    file_queue: asyncio.Queue[str] = asyncio.Queue()

    if media_paths:
        # Parse MEDIA_PATHS (assumed comma-separated).
        paths = [
            os.path.expanduser(path.strip())
            for path in media_paths.split(",")
            if path.strip()
        ]

    # Fallback to XDG directories if MEDIA_PATHS is not set.
    if not media_paths:
        logger.warning("No paths set, defaulting to ~/Pictures and ~/Videos")
        paths = [
            os.path.expanduser("~/Pictures"),
            os.path.expanduser("~/Videos"),
        ]

    # First, scan the provided directories for existing media files.
    await scan_existing_files(paths, db, new_file_event)

    loop = asyncio.get_running_loop()

    # Create and start watchdog observers for each media path.
    observers = []
    for path in paths:
        if os.path.isdir(path):
            event_handler = MediaFileHandler(file_queue, loop)
            observer = Observer()
            observer.schedule(event_handler, path=path, recursive=True)
            observer.start()
            observers.append(observer)
            logger.info(f"Started watching directory: {path}")
        else:
            logger.warning(f"MEDIA_PATHS contains invalid directory: {path}")

    # Register signal handlers for graceful shutdown.
    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)

    # Create asynchronous tasks for both the watcher and uploader.
    watcher_task = asyncio.create_task(watcher(db, file_queue))
    uploader_task = asyncio.create_task(
        uploader(db, BASE_URL, API_KEY, chunk_size, wifi_only, ssid, not_metered)
    )

    # Wait until shutdown_event is set (via signal)
    await shutdown_event.wait()
    logger.info("Shutdown event received, cancelling tasks...")

    # Cancel running tasks
    watcher_task.cancel()
    uploader_task.cancel()

    # Wait for tasks to cancel gracefully
    await asyncio.gather(watcher_task, uploader_task, return_exceptions=True)

    # Stop and join all observers.
    for observer in observers:
        observer.stop()
    for observer in observers:
        observer.join()

    await db.close()
    logger.info("Shutdown complete.")


def main():
    uvloop.install()
    asyncio.run(run())


if __name__ == "__main__":
    main()
