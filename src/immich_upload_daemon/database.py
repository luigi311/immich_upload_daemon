import aiosqlite
import os

from loguru import logger
from imohash import hashfile
from xdg.BaseDirectory import save_data_path

def get_db_path(db_name: str) -> str:
    """
    Returns a path for the database file using XDG Base Directory.
    This creates (if needed) and returns the application's data directory.
    """
    app_data_dir = save_data_path("immich_uploader")
    return os.path.join(app_data_dir, db_name)

class Database:
    def __init__(self, db_file: str) -> None:
        self.db_file: str = db_file
        self.conn: aiosqlite.Connection | None = None

    async def init_db(self) -> None:
        try:
            self.conn = await aiosqlite.connect(self.db_file)
            await self.conn.execute("PRAGMA journal_mode=WAL")

            # Create the media table if it doesn't exist.
            await self.conn.execute(
                "CREATE TABLE IF NOT EXISTS media (file_name TEXT PRIMARY KEY, file_hash TEXT, uploaded INTEGER)"
            )

            # Create an index on uploaded column for faster retrieval.
            await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_uploaded ON media (uploaded)")

            await self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise e

    @property
    def connection(self) -> aiosqlite.Connection:
        if self.conn is None:
            raise RuntimeError("Database connection is not initialized. Call init_db() first.")
        return self.conn

    async def add_media(self, file_name: str) -> None:
        """Insert or update the media in the database and reset the uploaded flag."""
        try:
            # Check if file_name and file_hash already exist in the database.
            file_hash = hashfile(file_name, hexdigest=True)
            async with self.connection.execute(
                "SELECT * FROM media WHERE file_name = ? AND file_hash = ?", (file_name, file_hash)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                # If the file_name and file_hash already exists, do nothing
                logger.info(f"Media {file_name} already exists in the database")
                return

            logger.info(f"Adding media {file_name}")
            await self.connection.execute(
                "INSERT OR REPLACE INTO media (file_name, file_hash, uploaded) VALUES (?, ?, 0)",
                (file_name, file_hash),
            )
            await self.connection.commit()
        except Exception as e:
            logger.error(f"Error adding media {file_name}: {e}")
            raise e

    async def mark_uploaded(self, file_name: str) -> None:
        try:
            logger.info(f"Marking {file_name} as uploaded")

            await self.connection.execute("UPDATE media SET uploaded = 1 WHERE file_name = ?", (file_name,))
            await self.connection.commit()
        except Exception as e:
            logger.error(f"Error marking {file_name} as uploaded: {e}")
            raise e

    async def get_unuploaded(self) -> list[str]:
        try:
            async with self.connection.execute("SELECT file_name FROM media WHERE uploaded = 0") as cursor:
                rows = await cursor.fetchall()

                if rows:
                    return [row[0] for row in rows]
                return [] 
        except Exception as e:
            logger.error(f"Error retrieving unuploaded media: {e}")
            return []

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
