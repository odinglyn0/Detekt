import json
import threading
import time

from sightengine.client import SightengineClient
import structlog

from utils.secrets import get_secret

import random

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
    threshold = float(get_secret("DTKT_AI_THRESHOLD"))

    client_ai = _get_client()
    client_df = _get_client()

    output_ai = client_ai.check("genai").set_url(image_url)
    if output_ai.get("status") == "failure":
        raise RuntimeError(f"sightengine genai failed: {output_ai.get('error', {}).get('message', 'unknown')}")

    output_df = client_df.check("deepfake").set_url(image_url)
    if output_df.get("status") == "failure":
        raise RuntimeError(f"sightengine deepfake failed: {output_df.get('error', {}).get('message', 'unknown')}")

    ai_score = output_ai.get("type", {}).get("ai_generated", 0.0)
    deepfake_score = output_df.get("type", {}).get("deepfake", 0.0)
    return {
        "dtkt_ai_score": ai_score,
        "dtkt_deepfake_score": deepfake_score,
        "dtkt_is_ai": ai_score > threshold,
        "dtkt_is_deepfake": deepfake_score > threshold,
        "dtkt_raw": {"genai": output_ai, "deepfake": output_df},
    }


def check_video(video_url: str) -> dict:
    threshold = float(get_secret("DTKT_AI_THRESHOLD"))
    client_ai = _get_client()
    client_df = _get_client()

    output_ai = client_ai.check("genai").video_sync(video_url)
    if output_ai.get("status") == "failure":
        raise RuntimeError(f"sightengine genai failed: {output_ai.get('error', {}).get('message', 'unknown')}")

    output_df = client_df.check("deepfake").video_sync(video_url)
    if output_df.get("status") == "failure":
        raise RuntimeError(f"sightengine deepfake failed: {output_df.get('error', {}).get('message', 'unknown')}")

    frames_ai = output_ai.get("data", {}).get("frames", [])
    frames_df = output_df.get("data", {}).get("frames", [])

    if not frames_ai and not frames_df:
        return {
            "dtkt_ai_score": 0.0,
            "dtkt_deepfake_score": 0.0,
            "dtkt_is_ai": False,
            "dtkt_is_deepfake": False,
            "dtkt_raw": {"genai": output_ai, "deepfake": output_df},
        }

    ai_scores = [f.get("type", {}).get("ai_generated", 0.0) for f in frames_ai]
    deepfake_scores = [f.get("type", {}).get("deepfake", 0.0) for f in frames_df]
    avg_ai = sum(ai_scores) / len(ai_scores) if ai_scores else 0.0
    avg_deepfake = sum(deepfake_scores) / len(deepfake_scores) if deepfake_scores else 0.0

    return {
        "dtkt_ai_score": avg_ai,
        "dtkt_deepfake_score": avg_deepfake,
        "dtkt_is_ai": avg_ai > threshold,
        "dtkt_is_deepfake": avg_deepfake > threshold,
        "dtkt_raw": {"genai": output_ai, "deepfake": output_df},
    }


def format_carousel_result(
    tagger: str,
    image_results: list[dict],
) -> str:
    threshold = float(get_secret("DTKT_AI_THRESHOLD"))
    low_min = float(get_secret("DTKT_LOW_CONFIDENCE_MIN"))
    low_max = float(get_secret("DTKT_LOW_CONFIDENCE_MAX"))

    parts = []
    for r in image_results:
        idx = r["index"]
        ai_pct = r["ai_score"] * 100
        df_pct = r["deepfake_score"] * 100

        if r.get("error"):
            parts.append(f"#{idx}: couldn't scan")
            continue

        if r["is_ai"] and ai_pct > low_max:
            parts.append(f"#{idx}: AI ({ai_pct:.0f}%)")
        elif r["is_deepfake"] and df_pct > low_max:
            parts.append(f"#{idx}: deepfake ({df_pct:.0f}%)")
        else:
            top = max(ai_pct, df_pct)
            if low_min <= top <= low_max:
                parts.append(f"#{idx}: unsure ({top:.0f}%)")
            else:
                real_conf = (1 - r["ai_score"]) * 100
                parts.append(f"#{idx}: real ({real_conf:.0f}%)")

    return f"@{tagger} " + ", ".join(parts)


def format_result(
    tagger: str,
    media_type: str,
    is_ai: bool,
    ai_score: float,
    is_deepfake: bool,
    deepfake_score: float,
) -> str:
    type_label = "photo" if media_type == "photo" else "video"
    ai_pct = ai_score * 100
    df_pct = deepfake_score * 100

    low_min = float(get_secret("DTKT_LOW_CONFIDENCE_MIN"))
    low_max = float(get_secret("DTKT_LOW_CONFIDENCE_MAX"))

    if is_ai and ai_pct > low_max:
        conf = ai_pct
        return random.choice(
            [
                f"@{tagger} yep, that's AI ({conf:.0f}% sure)",
                f"@{tagger} AI generated. {conf:.0f}% confident.",
                f"@{tagger} AI. {conf:.0f}%.",
            ]
        )

    if is_deepfake and df_pct > low_max:
        conf = df_pct
        return random.choice(
            [
                f"@{tagger} real {type_label} but the face is swapped ({conf:.0f}% sure)",
                f"@{tagger} deepfake detected. {conf:.0f}% confident.",
            ]
        )

    top_score = max(ai_pct, df_pct)
    if low_min <= top_score <= low_max:
        return random.choice(
            [
                f"@{tagger} not sure on this one ({top_score:.0f}% AI generated/manipulated)",
                f"@{tagger} inconclusive. {top_score:.0f}% AI generated/manipulated.",
            ]
        )

    real_conf = (1 - ai_score) * 100
    return random.choice(
        [
            f"@{tagger} looks real to me ({real_conf:.0f}% sure)",
            f"@{tagger} it's not AI. {real_conf:.0f}% confident.",
            f"@{tagger} real. {real_conf:.0f}%.",
        ]
    )
