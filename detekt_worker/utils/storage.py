import asyncio
import datetime
import mimetypes
from urllib.parse import urlparse

import httpx
from google.cloud import storage as gcs
import structlog

from utils.gcp_credentials import get_credentials, get_project_id
from utils.secrets import get_secret, get_secret_optional

logger = structlog.get_logger()

_client: gcs.Client | None = None
_bucket: gcs.Bucket | None = None


def _get_bucket() -> gcs.Bucket:
    global _client, _bucket
    if _bucket is not None:
        return _bucket

    dtkt_bucket_name = get_secret("DTKT_BUCKET_NAME")

    creds = get_credentials()
    project = get_project_id()
    kwargs = {}
    if creds:
        kwargs["credentials"] = creds
    if project:
        kwargs["project"] = project

    _client = gcs.Client(**kwargs)
    _bucket = _client.bucket(dtkt_bucket_name)
    logger.info(
        "dtkt-storage-init", bucket=dtkt_bucket_name, explicit_creds=creds is not None
    )
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


def _get_proxy_url() -> str | None:
    return get_secret_optional("DTKT_PROXY") or None


async def upload_video(
    video_id: str, download_url: str, headers: dict | None = None
) -> str:
    bucket = _get_bucket()

    proxy = _get_proxy_url()
    async with httpx.AsyncClient(proxy=proxy) as client:
        if not isinstance(download_url, str):
            raise ValueError(
                f"download_url is {type(download_url).__name__}, not str: {str(download_url)[:200]}"
            )
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


async def upload_video_bytes(video_id: str, data: bytes) -> str:
    bucket = _get_bucket()
    blob_path = f"vids/{video_id}/video.mp4"
    blob = bucket.blob(blob_path)
    await asyncio.to_thread(blob.upload_from_string, data, "video/mp4")
    logger.info("dtkt-video-uploaded", path=blob_path, size=len(data))
    return blob_path


async def upload_slideshow_images(
    video_id: str, image_urls: list[str]
) -> tuple[list[str], int, list[int]]:
    bucket = _get_bucket()
    paths = []
    original_indices = []

    proxy = _get_proxy_url()
    async with httpx.AsyncClient(proxy=proxy) as client:
        for idx, url in enumerate(image_urls, start=1):
            if not isinstance(url, str):
                logger.warning(
                    "dtkt-bad-image-url",
                    video_id=video_id,
                    idx=idx,
                    url_type=type(url).__name__,
                    url_value=str(url)[:200],
                )
                continue
            try:
                resp = await client.get(url, timeout=60, follow_redirects=True)
                resp.raise_for_status()
            except Exception as exc:
                logger.warning(
                    "dtkt-image-download-failed",
                    video_id=video_id,
                    idx=idx,
                    error=str(exc),
                )
                continue

            content_type = resp.headers.get("content-type")
            ext = _guess_extension(url, content_type)
            blob_path = f"pics/{video_id}/{idx}.{ext}"

            blob = bucket.blob(blob_path)
            await asyncio.to_thread(
                blob.upload_from_string, resp.content, content_type or "image/jpeg"
            )
            paths.append(blob_path)
            original_indices.append(idx)

    quantity = len(paths)
    logger.info(
        "dtkt-slideshow-uploaded",
        video_id=video_id,
        count=quantity,
        indices=original_indices,
    )
    return paths, quantity, original_indices


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


async def get_all_photo_blob_paths(vid: str) -> list[str]:
    bucket = _get_bucket()
    prefix = f"pics/{vid}/"
    blobs = await asyncio.to_thread(lambda: list(bucket.list_blobs(prefix=prefix)))
    return sorted([b.name for b in blobs])
