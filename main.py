import asyncio
import os
import signal
from dotenv import load_dotenv
from loguru import logger
from xdg.BaseDirectory import save_data_path

from src.immich import upload
from src.database import Database

load_dotenv(override=True)

# A global event to signal shutdown
shutdown_event = asyncio.Event()

def shutdown():
    logger.info("Received shutdown signal, initiating graceful shutdown...")
    shutdown_event.set()

async def watcher(db: Database):
    while not shutdown_event.is_set():
        file_path = "image.jpg"
        if os.path.exists(file_path):
            await db.add_media(file_path, "hash")

        await asyncio.sleep(10)

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
    BASE_URL = os.getenv("BASE_URL", None)
    API_KEY = os.getenv("API_KEY", None)

    if not BASE_URL or not API_KEY:
        logger.error("Please set BASE_URL and API_KEY in .env file")
        return

    # Strip trailing slashes
    BASE_URL = BASE_URL.rstrip("/")

    db = Database(get_db_path("files.db"))
    await db.init_db()

    # Register signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)

    # Create asynchronous tasks for both the watcher and uploader.
    watcher_task = asyncio.create_task(watcher(db))
    uploader_task = asyncio.create_task(uploader(db, BASE_URL, API_KEY))
    
    # Wait until shutdown_event is set (via signal)
    await shutdown_event.wait()
    logger.info("Shutdown event received, cancelling tasks...")

    # Cancel running tasks
    watcher_task.cancel()
    uploader_task.cancel()

    # Wait for tasks to cancel gracefully
    await asyncio.gather(watcher_task, uploader_task, return_exceptions=True)
    await db.close()
    logger.info("Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())
