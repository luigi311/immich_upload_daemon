import aiohttp
import os

from datetime import datetime
from loguru import logger

from .files import file_chunk_generator

async def upload(base_url: str, api_key: str, file: str) -> bool:
    logger.info(f'Uploading {file}...')
    stats = os.stat(file)
    file_size = os.stat(file).st_size

    headers = {
        'Accept': 'application/json',
        'x-api-key': api_key,
    }

    # Convert timestamps to ISO format for JSON compatibility.
    data = {
        'deviceAssetId': f'{file}-{stats.st_mtime}',
        'deviceId': 'python',
        'fileCreatedAt': datetime.fromtimestamp(stats.st_mtime).isoformat(),
        'fileModifiedAt': datetime.fromtimestamp(stats.st_mtime).isoformat(),
        'fileSize': str(file_size),
        'isFavorite': 'false',
    }

    timeout = aiohttp.ClientTimeout(total=60*60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Build the form-data for upload.
            form = aiohttp.FormData()
            for key, value in data.items():
                form.add_field(key, value)
            
            file_iter = file_chunk_generator(file, chunk_size=8192)
            file_payload = aiohttp.AsyncIterablePayload(
                file_iter,
                size=file_size,
                content_type='application/octet-stream',
            )
            form.add_field(
                'assetData',
                file_payload,
                filename=os.path.basename(file),
                content_type='application/octet-stream'
            )

            async with session.post(f'{base_url}/assets', headers=headers, data=form) as response:
                status = response.status
                if status not in [200, 201]:
                    logger.error(f'Failed to upload {file}: {await response.text()}')
                    return False

                response_json = await response.json()
                status = response_json.get('status')
                if status == 'created':
                    logger.success(f'{file} uploaded successfully')
                    return True
                elif status == 'duplicate':
                    logger.warning(f'{file} is duplicate of {response_json.get("id")}')
                    return True
                logger.error(f'Failed to upload {file}: {response_json}')
                return False
    except Exception as e:
        logger.error(f"Failed to upload {file}: {e}")
        return False
