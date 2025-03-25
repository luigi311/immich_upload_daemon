import asyncio
import os
import signal

from dotenv import load_dotenv
from loguru import logger
from xdg.BaseDirectory import save_data_path
from watchdog.observers import Observer

from src.immich import upload
from src.database import Database
from src.files import MediaFileHandler

load_dotenv(override=True)

# A global event to signal shutdown
shutdown_event = asyncio.Event()


def shutdown():
    logger.info("Received shutdown signal, initiating graceful shutdown...")
    shutdown_event.set()


async def watcher(db: Database, queue: asyncio.Queue):
    """
    Asynchronous watcher that processes file paths from the queue.
    """
    while not shutdown_event.is_set():
        try:
            # Wait for a new file path from the watchdog handler.
            file_path = await asyncio.wait_for(queue.get(), timeout=10)

            if os.path.exists(file_path):
                await db.add_media(file_path, "hash")

            queue.task_done()
        except asyncio.TimeoutError:
            # No new files found during timeout; continue checking.
            continue


async def uploader(db: Database, base_url: str, api_key: str):
    while not shutdown_event.is_set():
        unuploaded = await db.get_unuploaded()

        for file_name in unuploaded:
            if await upload(base_url, api_key, file_name):
                await db.mark_uploaded(file_name)
        await asyncio.sleep(5)


def get_db_path(db_name: str) -> str:
    """
    Returns a path for the database file using XDG Base Directory.
    This creates (if needed) and returns the application's data directory.
    """
    app_data_dir = save_data_path("immich_uploader")
    return os.path.join(app_data_dir, db_name)


async def main():
    BASE_URL = os.getenv("BASE_URL")
    API_KEY = os.getenv("API_KEY")
    media_paths = os.getenv("MEDIA_PATHS")

    if not BASE_URL or not API_KEY:
        logger.error("Please set BASE_URL and API_KEY in .env file")
        return

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
    uploader_task = asyncio.create_task(uploader(db, BASE_URL, API_KEY))

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


if __name__ == "__main__":
    asyncio.run(main())
