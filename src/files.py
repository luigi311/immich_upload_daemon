import asyncio

from loguru import logger
from watchdog.events import FileSystemEventHandler

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


