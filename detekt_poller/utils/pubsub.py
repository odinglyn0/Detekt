import json
import os

from google.cloud import pubsub_v1
from google.api_core import retry as api_retry
import structlog

logger = structlog.get_logger()

_publisher: pubsub_v1.PublisherClient | None = None
_topic_path: str | None = None


def _get_publisher() -> tuple[pubsub_v1.PublisherClient, str]:
    global _publisher, _topic_path
    if _publisher is not None:
        return _publisher, _topic_path

    dtkt_gcp_project = os.environ["DTKT_GCP_PROJECT"]
    dtkt_pubsub_topic = os.environ["DTKT_PUBSUB_TOPIC"]

    _publisher = pubsub_v1.PublisherClient()
    _topic_path = _publisher.topic_path(dtkt_gcp_project, dtkt_pubsub_topic)
    logger.info("dtkt-pubsub-init", topic=_topic_path)
    return _publisher, _topic_path


def publish_mention(vid: str, cid: str, username: str, is_video: int, message: str, quantity: int | None = None) -> None:
    publisher, topic = _get_publisher()

    payload = {
        "vid": vid,
        "cid": cid,
        "u": username,
        "t": is_video,
        "m": message,
    }

    if is_video == 0 and quantity is not None:
        payload["q"] = quantity

    data = json.dumps(payload).encode("utf-8")

    future = publisher.publish(
        topic,
        data,
        retry=api_retry.Retry(deadline=60),
    )
    message_id = future.result(timeout=30)
    logger.info("dtkt-mention-published", message_id=message_id, payload=payload)
