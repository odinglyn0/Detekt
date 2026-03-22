import json
import os
import signal
import time
import threading

from google.cloud import pubsub_v1
import structlog

from utils.secrets import get_secret
from utils.rate_limiter import is_rate_limited
from utils.firestore import get_cached_result, try_claim_scan, wait_for_result, store_scan_result
from utils.sightengine import check_image, check_video, format_result
from utils.storage import get_signed_url, get_video_blob_path, get_photo_blob_path
from utils.tiktok import reply_sync

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger()

dtkt_running = True
_processing_lock = threading.Lock()


def _handle_signal(sig, frame):
    global dtkt_running
    logger.info("dtkt-shutdown-requested", signal=sig)
    dtkt_running = False


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def _reply_with_result(vid: str, cid: str, username: str, media_type: str, result: dict) -> None:
    result_text = format_result(
        tagger=username,
        media_type=media_type,
        is_ai=result["dtkt_is_ai"],
        ai_score=result["dtkt_ai_score"],
    )
    try:
        reply_sync(vid, cid, username, result_text)
    except Exception as exc:
        logger.warning("dtkt-reply-error", vid=vid, error=str(exc))
    logger.info("dtkt-result-sent", vid=vid, result=result_text)


def process_message(message: pubsub_v1.subscriber.message.Message) -> None:
    with _processing_lock:
        _handle_message(message)


def _handle_message(message: pubsub_v1.subscriber.message.Message) -> None:
    try:
        data = json.loads(message.data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error("dtkt-message-parse-error", error=str(exc))
        message.ack()
        return

    vid = data.get("vid")
    cid = data.get("cid")
    username = data.get("u")
    content_type = data.get("t")
    comment_message = data.get("m", "")
    photo_quantity = data.get("q", 0)

    logger.info("dtkt-message-received", vid=vid, cid=cid, user=username, type=content_type)

    if content_type == 0 and photo_quantity > 1:
        logger.info("dtkt-slideshow-skipped", vid=vid, q=photo_quantity)
        message.ack()
        return

    if is_rate_limited(username):
        message.nack()
        return

    media_type = "video" if content_type == 1 else "photo"

    claim = try_claim_scan(vid)

    if claim == "cached":
        cached = get_cached_result(vid)
        if cached:
            _reply_with_result(vid, cid, username, media_type, cached)
        message.ack()
        return

    if claim == "waiting":
        logger.info("dtkt-waiting-for-inflight", vid=vid)
        result = wait_for_result(vid)
        if result:
            _reply_with_result(vid, cid, username, media_type, result)
        else:
            logger.warning("dtkt-wait-failed-nack", vid=vid)
            message.nack()
            return
        message.ack()
        return

    try:
        if content_type == 1:
            blob_path = get_video_blob_path(vid)
            if not blob_path:
                logger.warning("dtkt-video-not-found-in-bucket", vid=vid)
                message.nack()
                return
            signed_url = get_signed_url(blob_path)
            scan = check_video(signed_url)
        else:
            blob_path = get_photo_blob_path(vid)
            if not blob_path:
                logger.warning("dtkt-photo-not-found-in-bucket", vid=vid)
                message.nack()
                return
            signed_url = get_signed_url(blob_path)
            scan = check_image(signed_url)

    except Exception as exc:
        logger.error("dtkt-scan-error", vid=vid, error=str(exc))
        message.nack()
        return

    store_scan_result(
        media_id=vid,
        media_type=media_type,
        ai_score=scan["dtkt_ai_score"],
        is_ai=scan["dtkt_is_ai"],
        vid=vid,
        cid=cid,
        username=username,
        message=comment_message,
        raw_response=scan["dtkt_raw"],
    )

    _reply_with_result(vid, cid, username, media_type, scan)
    message.ack()


def run() -> None:
    dtkt_gcp_project = os.environ["DTKT_GCP_PROJECT"]
    dtkt_subscription = os.environ["DTKT_PUBSUB_SUBSCRIPTION"]

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(dtkt_gcp_project, dtkt_subscription)

    flow_control = pubsub_v1.types.FlowControl(max_messages=5)

    streaming_pull = subscriber.subscribe(
        subscription_path,
        callback=process_message,
        flow_control=flow_control,
    )

    logger.info("dtkt-scanner-started", subscription=subscription_path)

    try:
        while dtkt_running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        streaming_pull.cancel()
        streaming_pull.result()
        logger.info("dtkt-scanner-stopped")


if __name__ == "__main__":
    run()
