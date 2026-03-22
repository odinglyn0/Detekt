import mimetypes
import os
from urllib.parse import urlparse

import httpx
from google.cloud import storage as gcs
import structlog

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


def upload_video(video_id: str, download_url: str, headers: dict | None = None) -> str:
    bucket = _get_bucket()

    resp = httpx.get(download_url, headers=headers or {}, timeout=120, follow_redirects=True)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type")
    ext = _guess_extension(download_url, content_type)
    blob_path = f"vids/{video_id}/video.{ext}"

    blob = bucket.blob(blob_path)
    blob.upload_from_string(resp.content, content_type=content_type or "video/mp4")
    logger.info("dtkt-video-uploaded", path=blob_path, size=len(resp.content))
    return blob_path


def upload_slideshow_images(video_id: str, image_urls: list[str]) -> tuple[list[str], int]:
    bucket = _get_bucket()
    paths = []

    for idx, url in enumerate(image_urls, start=1):
        resp = httpx.get(url, timeout=60, follow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type")
        ext = _guess_extension(url, content_type)
        blob_path = f"pics/{video_id}/{idx}.{ext}"

        blob = bucket.blob(blob_path)
        blob.upload_from_string(resp.content, content_type=content_type or "image/jpeg")
        paths.append(blob_path)

    quantity = len(paths)
    logger.info("dtkt-slideshow-uploaded", video_id=video_id, count=quantity)
    return paths, quantity
