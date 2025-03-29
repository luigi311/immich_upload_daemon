import asyncio
import os

from loguru import logger
from watchdog.events import FileSystemEventHandler

from .database import Database

# Source: https://github.com/immich-app/immich/blob/main/docs/docs/features/supported-formats.md?plain=1
SUPPORTED_MEDIA_EXTENSIONS = (
    # Image extensions
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".jp2",
    ".webp",
    ".jpg",
    ".jpe",
    ".insp",
    ".jxl",
    ".png",
    ".psd",
    ".raw",
    ".rw2",
    ".svg",
    ".tif",
    ".tiff",
    # Video extensions
    ".3gp",
    ".3gpp",
    ".avi",
    ".flv",
    ".m4v",
    ".mkv",
    ".mts",
    ".m2ts",
    ".m2t",
    ".mp4",
    ".insv",
    ".mpg",
    ".mpe",
    ".mpeg",
    ".mov",
    ".webm",
    ".wmv",
)

class MediaFileHandler(FileSystemEventHandler):
    """
    Watchdog event handler that looks for newly created media files.
    Only files with common media extensions are enqueued.
    """

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        self.queue = queue
        self.loop = loop
        super().__init__()

    def on_created(self, event):
        # Only process files (not directories) with typical media extensions.
        if not event.is_directory and event.src_path.lower().endswith(
            SUPPORTED_MEDIA_EXTENSIONS
        ):
            logger.info(f"Detected new media file: {event.src_path}")
            self.loop.call_soon_threadsafe(self.queue.put_nowait, event.src_path)


async def scan_existing_files(paths: list[str], db: Database, new_file_event: asyncio.Event) -> None:
    """
    Scan the provided directories for existing media files and add them to the database.
    The scanning is performed in a thread to avoid blocking the event loop.
    """
    logger.info("Scanning existing files in provided directories...")
    for path in paths:
        # Use asyncio.to_thread to run os.walk in a thread
        files = await asyncio.to_thread(
            lambda: [
                os.path.join(root, f)
                for root, dirs, files in os.walk(path)
                for f in files
                if f.lower().endswith(SUPPORTED_MEDIA_EXTENSIONS)
            ]
        )
        for file_path in files:
            if os.path.exists(file_path):
                try:
                    if await db.add_media(file_path):
                        new_file_event.set()

                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")

    # Check if unuploaded and if there is any then start the uploader incase there were lingering files
    if await db.get_unuploaded():
        new_file_event.set()

    logger.info("Finished scanning existing files.")
