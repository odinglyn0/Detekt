import datetime
import os

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


def get_signed_url(blob_path: str, expiry_minutes: int = 30) -> str:
    bucket = _get_bucket()
    blob = bucket.blob(blob_path)
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=expiry_minutes),
        method="GET",
    )
    return url


def get_video_blob_path(vid: str) -> str | None:
    bucket = _get_bucket()
    prefix = f"vids/{vid}/"
    blobs = list(bucket.list_blobs(prefix=prefix, max_results=1))
    if blobs:
        return blobs[0].name
    return None


def get_photo_blob_path(vid: str) -> str | None:
    bucket = _get_bucket()
    prefix = f"pics/{vid}/"
    blobs = list(bucket.list_blobs(prefix=prefix, max_results=1))
    if blobs:
        return blobs[0].name
    return None
