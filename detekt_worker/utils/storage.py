import asyncio
import datetime
import mimetypes
import os
from urllib.parse import urlparse

import httpx
from google.cloud import storage as gcs
from proxyproviders.algorithms import Random
from proxyproviders.models.proxy import ProxyFormat
import structlog

from utils.proxy import get_proxy_provider

logger = structlog.get_logger()

_client: gcs.Client | None = None
_bucket: gcs.Bucket | None = None


def _get_bucket() -> gcs.Bucket:
    global _client, _bucket
    if _bucket is not None:
        return _bucket

    dtkt_bucket_name = os.environ["DTKT_BUCKET_NAME"]
    _client = gcs.Client()
    _bucket = _client.bucket(dtkt_bucket_name)
    logger.info("dtkt-storage-init", bucket=dtkt_bucket_name)
    return _bucket


def _guess_extension(url: str, content_type: str | None) -> str:
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ext.lstrip(".")

    path = urlparse(url).path
    if "." in path.split("/")[-1]:
        return path.split(".")[-1].split("?")[0]

    return "mp4"


async def upload_video(
    video_id: str, download_url: str, headers: dict | None = None
) -> str:
    bucket = _get_bucket()

    proxy = get_proxy_provider().get_proxy(Random()).format(ProxyFormat.HTTPX)
    async with httpx.AsyncClient(proxies=proxy) as client:
        resp = await client.get(
            download_url, headers=headers or {}, timeout=120, follow_redirects=True
        )
        resp.raise_for_status()

    content_type = resp.headers.get("content-type")
    ext = _guess_extension(download_url, content_type)
    blob_path = f"vids/{video_id}/video.{ext}"

    blob = bucket.blob(blob_path)
    await asyncio.to_thread(
        blob.upload_from_string, resp.content, content_type or "video/mp4"
    )
    logger.info("dtkt-video-uploaded", path=blob_path, size=len(resp.content))
    return blob_path


async def upload_slideshow_images(
    video_id: str, image_urls: list[str]
) -> tuple[list[str], int]:
    bucket = _get_bucket()
    paths = []

    proxy = get_proxy_provider().get_proxy(Random()).format(ProxyFormat.HTTPX)
    async with httpx.AsyncClient(proxies=proxy) as client:
        for idx, url in enumerate(image_urls, start=1):
            resp = await client.get(url, timeout=60, follow_redirects=True)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type")
            ext = _guess_extension(url, content_type)
            blob_path = f"pics/{video_id}/{idx}.{ext}"

            blob = bucket.blob(blob_path)
            await asyncio.to_thread(
                blob.upload_from_string, resp.content, content_type or "image/jpeg"
            )
            paths.append(blob_path)

    quantity = len(paths)
    logger.info("dtkt-slideshow-uploaded", video_id=video_id, count=quantity)
    return paths, quantity


async def get_signed_url(blob_path: str, expiry_minutes: int = 30) -> str:
    bucket = _get_bucket()
    blob = bucket.blob(blob_path)
    url = await asyncio.to_thread(
        blob.generate_signed_url,
        version="v4",
        expiration=datetime.timedelta(minutes=expiry_minutes),
        method="GET",
    )
    return url


async def get_video_blob_path(vid: str) -> str | None:
    bucket = _get_bucket()
    prefix = f"vids/{vid}/"
    blobs = await asyncio.to_thread(
        lambda: list(bucket.list_blobs(prefix=prefix, max_results=1))
    )
    if blobs:
        return blobs[0].name
    return None


async def get_photo_blob_path(vid: str) -> str | None:
    bucket = _get_bucket()
    prefix = f"pics/{vid}/"
    blobs = await asyncio.to_thread(
        lambda: list(bucket.list_blobs(prefix=prefix, max_results=1))
    )
    if blobs:
        return blobs[0].name
    return None
