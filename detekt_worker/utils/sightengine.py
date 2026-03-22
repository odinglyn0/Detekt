import json
import threading
import time

from sightengine.client import SightengineClient
import structlog

from utils.secrets import get_secret

logger = structlog.get_logger()

_clients: list[SightengineClient] = []
_lock = threading.Lock()
_index = 0
_last_accs_hash: str | None = None
_last_init: float = 0

DTKT_CLIENT_REFRESH_INTERVAL = 120


def _build_clients() -> list[SightengineClient]:
    clients = []
    dtkt_use_pool = get_secret("DTKT_SIGHTENGINE_ACC_POOL").lower() in (
        "true",
        "1",
        "yes",
    )

    if dtkt_use_pool:
        raw = get_secret("DTKT_SIGHTENGINE_ACCS")
        accounts = json.loads(raw)
        for api_user, api_secret in accounts.items():
            clients.append(SightengineClient(api_user, api_secret))
        logger.info("dtkt-sightengine-pool-init", count=len(clients))
    else:
        api_user = get_secret("DTKT_SIGHTENGINE_API_USER")
        api_secret = get_secret("DTKT_SIGHTENGINE_API_SECRET")
        clients.append(SightengineClient(api_user, api_secret))
        logger.info("dtkt-sightengine-single-init")

    return clients


def _get_client() -> SightengineClient:
    global _clients, _index, _last_accs_hash, _last_init

    with _lock:
        now = time.monotonic()
        needs_refresh = (
            not _clients or (now - _last_init) > DTKT_CLIENT_REFRESH_INTERVAL
        )

        if needs_refresh:
            try:
                raw = (
                    get_secret("DTKT_SIGHTENGINE_ACCS")
                    if get_secret("DTKT_SIGHTENGINE_ACC_POOL").lower()
                    in ("true", "1", "yes")
                    else ""
                )
            except SystemExit:
                raw = ""

            if raw != _last_accs_hash or not _clients:
                _clients = _build_clients()
                _last_accs_hash = raw

            _last_init = now

        client = _clients[_index % len(_clients)]
        _index += 1

    return client


def check_image(image_url: str) -> dict:
    client = _get_client()
    threshold = float(get_secret("DTKT_AI_THRESHOLD"))
    output = client.check("genai").set_url(image_url)
    ai_score = output.get("type", {}).get("ai_generated", 0.0)
    return {
        "dtkt_ai_score": ai_score,
        "dtkt_is_ai": ai_score > threshold,
        "dtkt_raw": output,
    }


def check_video(video_url: str) -> dict:
    client = _get_client()
    threshold = float(get_secret("DTKT_AI_THRESHOLD"))
    output = client.check("genai").video_sync(video_url)

    frames = output.get("data", {}).get("frames", [])
    if not frames:
        return {
            "dtkt_ai_score": 0.0,
            "dtkt_is_ai": False,
            "dtkt_raw": output,
        }

    scores = [f.get("type", {}).get("ai_generated", 0.0) for f in frames]
    avg_score = sum(scores) / len(scores)

    return {
        "dtkt_ai_score": avg_score,
        "dtkt_is_ai": avg_score > threshold,
        "dtkt_raw": output,
    }


def format_result(tagger: str, media_type: str, is_ai: bool, ai_score: float) -> str:
    type_label = "photo" if media_type == "photo" else "video"
    header = f"@{tagger} - the {type_label}"

    if is_ai:
        verdict = "was AI generated!"
    else:
        verdict = "wasn't AI generated!"

    confidence = f"The algo was {ai_score * 100:.0f}% confident."

    return f"{header} {verdict} {confidence}"
