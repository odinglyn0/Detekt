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
    logger.info("dtkt-poller-firestore-init")
    return _db


def is_comment_processed(comment_id: str) -> bool:
    db = _get_db()
    collection = os.environ["DTKT_FIRESTORE_COMMENTS_COLLECTION"]
    doc = db.collection(collection).document(comment_id).get()
    return doc.exists


def mark_comment_processed(comment_id: str, vid: str, username: str) -> None:
    db = _get_db()
    collection = os.environ["DTKT_FIRESTORE_COMMENTS_COLLECTION"]
    db.collection(collection).document(comment_id).set({
        "dtkt_vid": vid,
        "dtkt_username": username,
        "dtkt_processed_at": firestore.SERVER_TIMESTAMP,
    })


def circuit_breaker_check() -> bool:
    db = _get_db()
    collection = os.environ["DTKT_FIRESTORE_CIRCUIT_COLLECTION"]
    doc_id = os.environ["DTKT_FIRESTORE_CIRCUIT_DOC"]
    doc_ref = db.collection(collection).document(doc_id)
    now = time.time()

    cb_max = int(get_secret("DTKT_CIRCUIT_BREAKER_MAX"))
    cb_window = float(get_secret("DTKT_CIRCUIT_BREAKER_WINDOW"))
    cb_cooldown = float(get_secret("DTKT_CIRCUIT_BREAKER_COOLDOWN"))

    doc = doc_ref.get()
    data = doc.to_dict() if doc.exists else {}

    open_until = data.get("dtkt_open_until", 0)
    if now < open_until:
        return False

    timestamps = [t for t in data.get("dtkt_timestamps", []) if t > now - cb_window]
    timestamps.append(now)

    if len(timestamps) > cb_max:
        doc_ref.set({
            "dtkt_open_until": now + cb_cooldown,
            "dtkt_timestamps": [],
            "dtkt_tripped_at": firestore.SERVER_TIMESTAMP,
        })
        logger.error("dtkt-circuit-breaker-tripped", cooldown=cb_cooldown)
        return False

    doc_ref.set({
        "dtkt_open_until": 0,
        "dtkt_timestamps": timestamps,
    })
    return True
