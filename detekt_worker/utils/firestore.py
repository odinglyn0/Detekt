import time

from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud import firestore as firestore_types
import structlog

from utils.gcp_credentials import get_credentials, get_project_id
from utils.secrets import get_secret

logger = structlog.get_logger()

_db: AsyncClient | None = None


def _get_db() -> AsyncClient:
    global _db
    if _db is not None:
        return _db

    creds = get_credentials()
    project = get_project_id()
    kwargs = {}
    if creds:
        kwargs["credentials"] = creds
    if project:
        kwargs["project"] = project

    _db = AsyncClient(database=get_secret("DTKT_FIRESTORE_DATABASE"), **kwargs)
    logger.info("dtkt-firestore-init", explicit_creds=creds is not None)
    return _db


def _scans_collection() -> str:
    return get_secret("DTKT_FIRESTORE_SCANS_COLLECTION")


async def get_cached_result(media_id: str) -> dict | None:
    db = _get_db()
    doc = await db.collection(_scans_collection()).document(media_id).get()
    if not doc.exists:
        return None

    data = doc.to_dict()
    if data.get("dtkt_status") == "complete":
        logger.info("dtkt-cache-hit", media_id=media_id)
        return data

    return None


async def is_known(media_id: str) -> bool:
    db = _get_db()
    doc = await db.collection(_scans_collection()).document(media_id).get()
    return doc.exists


async def is_mention_seen(cid: str) -> bool:
    db = _get_db()
    doc = await db.collection(_scans_collection()).document(f"mention:{cid}").get()
    return doc.exists


async def mark_mention_seen(cid: str, vid: str) -> None:
    db = _get_db()
    doc_ref = db.collection(_scans_collection()).document(f"mention:{cid}")
    await doc_ref.set(
        {
            "dtkt_status": "seen",
            "dtkt_cid": cid,
            "dtkt_vid": vid,
            "dtkt_seen_at": time.time(),
            "dtkt_created_at": firestore_types.SERVER_TIMESTAMP,
        }
    )


async def store_skipped(media_id: str, reason: str, cid: str | None = None) -> None:
    db = _get_db()
    batch = db.batch()

    doc_ref = db.collection(_scans_collection()).document(media_id)
    batch.set(doc_ref, {
        "dtkt_status": "skipped",
        "dtkt_media_id": media_id,
        "dtkt_skip_reason": reason,
        "dtkt_skipped_at": time.time(),
        "dtkt_created_at": firestore_types.SERVER_TIMESTAMP,
    })

    if cid:
        mention_ref = db.collection(_scans_collection()).document(f"mention:{cid}")
        batch.set(mention_ref, {
            "dtkt_status": "seen",
            "dtkt_cid": cid,
            "dtkt_vid": media_id,
            "dtkt_seen_at": time.time(),
            "dtkt_created_at": firestore_types.SERVER_TIMESTAMP,
        })

    await batch.commit()
    logger.info("dtkt-firestore-skipped", media_id=media_id, reason=reason)


async def store_scan_result(
    media_id: str,
    media_type: str,
    ai_score: float,
    is_ai: bool,
    deepfake_score: float,
    is_deepfake: bool,
    vid: str,
    cid: str,
    username: str,
    message: str,
    raw_response: dict,
) -> None:
    db = _get_db()
    doc_ref = db.collection(_scans_collection()).document(media_id)
    await doc_ref.set(
        {
            "dtkt_status": "complete",
            "dtkt_media_id": media_id,
            "dtkt_media_type": media_type,
            "dtkt_ai_score": ai_score,
            "dtkt_is_ai": is_ai,
            "dtkt_deepfake_score": deepfake_score,
            "dtkt_is_deepfake": is_deepfake,
            "dtkt_vid": vid,
            "dtkt_cid": cid,
            "dtkt_username": username,
            "dtkt_message": message,
            "dtkt_raw_response": raw_response,
            "dtkt_scanned_at": time.time(),
            "dtkt_created_at": firestore_types.SERVER_TIMESTAMP,
        }
    )
    logger.info("dtkt-firestore-stored", media_id=media_id, ai_score=ai_score)
