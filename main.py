import asyncio
import os
from dotenv import load_dotenv
from loguru import logger

from src.immich import upload
from src.database import Database

load_dotenv(override=True)

async def watcher(db: Database):
    while True:
        file_path = "image.jpg"
        if os.path.exists(file_path):
            await db.add_media(file_path, "hash")
   
        await asyncio.sleep(10)

async def uploader(db: Database, base_url: str, api_key: str):
    while True:
        unuploaded = await db.get_unuploaded()

        for file_name in unuploaded:
            if await upload(base_url, api_key, file_name):
                await db.mark_uploaded(file_name)
        await asyncio.sleep(5)

async def main():
    BASE_URL = os.getenv("BASE_URL", None)
    API_KEY = os.getenv("API_KEY", None)

    if not BASE_URL or not API_KEY:
        logger.error("Please set BASE_URL and API_KEY in .env file")
        return

    # Strip trailing slashes
    BASE_URL = BASE_URL.rstrip("/")

    db = Database("immich.db")
    await db.init_db()

    # Create asynchronous tasks for both the watcher and uploader.
    watcher_task = asyncio.create_task(watcher(db))
    uploader_task = asyncio.create_task(uploader(db, BASE_URL, API_KEY))
    
    try:
        await asyncio.gather(watcher_task, uploader_task)
    except asyncio.CancelledError:
        pass
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
