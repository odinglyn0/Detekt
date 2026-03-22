import os
import time

from google.cloud import firestore
import structlog

from utils.secrets import get_secret

logger = structlog.get_logger()

_db: firestore.Client | None = None


def _get_db() -> firestore.Client:
    global _db
    if _db is not None:
        return _db
    _db = firestore.Client()
    logger.info("dtkt-firestore-init")
    return _db


def _collection_name() -> str:
    return os.environ["DTKT_FIRESTORE_SCANS_COLLECTION"]


def get_cached_result(media_id: str) -> dict | None:
    db = _get_db()
    doc = db.collection(_collection_name()).document(media_id).get()
    if not doc.exists:
        return None

    data = doc.to_dict()
    if data.get("dtkt_status") == "complete":
        logger.info("dtkt-cache-hit", media_id=media_id)
        return data

    return None


def try_claim_scan(media_id: str) -> str:
    db = _get_db()
    doc_ref = db.collection(_collection_name()).document(media_id)
    now = time.time()

    @firestore.transactional
    def _claim(transaction):
        doc = doc_ref.get(transaction=transaction)
        if doc.exists:
            data = doc.to_dict()
            status = data.get("dtkt_status")

            if status == "complete":
                return "cached"

            if status == "in_progress":
                claimed_at = data.get("dtkt_claimed_at", 0)
                scan_ttl = int(get_secret("DTKT_SCAN_LOCK_TIMEOUT"))
                if now - claimed_at < scan_ttl:
                    return "waiting"

        transaction.set(doc_ref, {
            "dtkt_status": "in_progress",
            "dtkt_claimed_at": now,
        })
        return "claimed"

    transaction = db.transaction()
    return _claim(transaction)


def wait_for_result(media_id: str) -> dict | None:
    db = _get_db()
    doc_ref = db.collection(_collection_name()).document(media_id)
    poll_interval = int(get_secret("DTKT_POLL_INTERVAL"))
    poll_max_wait = int(get_secret("DTKT_POLL_MAX_WAIT"))
    waited = 0

    while waited < poll_max_wait:
        time.sleep(poll_interval)
        waited += poll_interval

        doc = doc_ref.get()
        if not doc.exists:
            return None

        data = doc.to_dict()
        if data.get("dtkt_status") == "complete":
            logger.info("dtkt-wait-resolved", media_id=media_id, waited=waited)
            return data

    logger.warning("dtkt-wait-timeout", media_id=media_id)
    return None


def store_scan_result(
    media_id: str,
    media_type: str,
    ai_score: float,
    is_ai: bool,
    vid: str,
    cid: str,
    username: str,
    message: str,
    raw_response: dict,
) -> None:
    db = _get_db()
    doc_ref = db.collection(_collection_name()).document(media_id)
    doc_ref.set({
        "dtkt_status": "complete",
        "dtkt_media_id": media_id,
        "dtkt_media_type": media_type,
        "dtkt_ai_score": ai_score,
        "dtkt_is_ai": is_ai,
        "dtkt_vid": vid,
        "dtkt_cid": cid,
        "dtkt_username": username,
        "dtkt_message": message,
        "dtkt_raw_response": raw_response,
        "dtkt_scanned_at": time.time(),
        "dtkt_created_at": firestore.SERVER_TIMESTAMP,
    })
    logger.info("dtkt-firestore-stored", media_id=media_id, ai_score=ai_score)
