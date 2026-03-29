import threading
import time

from sightengine.client import SightengineClient
import structlog

from utils.secrets import get_secret

import random

logger = structlog.get_logger()

_client: SightengineClient | None = None
_lock = threading.Lock()
_last_used: float = 0
_last_init: float = 0


def _get_refresh_interval() -> int:
    return int(get_secret("DTKT_SIGHTENGINE_REFRESH_INTERVAL"))


def _get_min_interval() -> float:
    return float(get_secret("DTKT_SIGHTENGINE_MIN_INTERVAL"))


def _build_client() -> SightengineClient:
    api_user = get_secret("DTKT_SIGHTENGINE_API_USER")
    api_secret = get_secret("DTKT_SIGHTENGINE_API_SECRET")
    logger.info("dtkt-sightengine-init")
    return SightengineClient(api_user, api_secret)


def _get_client() -> SightengineClient:
    global _client, _last_init, _last_used

    while True:
        with _lock:
            now = time.monotonic()
            needs_refresh = (
                _client is None or (now - _last_init) > _get_refresh_interval()
            )

            if needs_refresh:
                _client = _build_client()
                _last_init = now

            elapsed = now - _last_used
            min_interval = _get_min_interval()
            if elapsed >= min_interval:
                _last_used = now
                return _client

            wait_needed = min_interval - elapsed

        logger.debug("dtkt-sightengine-rate-wait", wait=f"{wait_needed:.2f}s")
        time.sleep(wait_needed)


def check_image(image_url: str) -> dict:
    threshold = float(get_secret("DTKT_AI_THRESHOLD"))

    client_ai = _get_client()
    client_df = _get_client()

    output_ai = client_ai.check("genai").set_url(image_url)
    if output_ai.get("status") == "failure":
        raise RuntimeError(
            f"sightengine genai failed: {output_ai.get('error', {}).get('message', 'unknown')}"
        )

    output_df = client_df.check("deepfake").set_url(image_url)
    if output_df.get("status") == "failure":
        raise RuntimeError(
            f"sightengine deepfake failed: {output_df.get('error', {}).get('message', 'unknown')}"
        )

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
        raise RuntimeError(
            f"sightengine genai failed: {output_ai.get('error', {}).get('message', 'unknown')}"
        )

    output_df = client_df.check("deepfake").video_sync(video_url)
    if output_df.get("status") == "failure":
        raise RuntimeError(
            f"sightengine deepfake failed: {output_df.get('error', {}).get('message', 'unknown')}"
        )

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
    avg_deepfake = (
        sum(deepfake_scores) / len(deepfake_scores) if deepfake_scores else 0.0
    )

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
                f"yep, that's AI ({conf:.0f}% sure)",
                f"AI generated. {conf:.0f}% confident.",
                f"AI. {conf:.0f}%.",
            ]
        )

    if is_deepfake and df_pct > low_max:
        conf = df_pct
        return random.choice(
            [
                f"real {type_label} but the face is swapped ({conf:.0f}% sure)",
                f"deepfake detected. {conf:.0f}% confident.",
            ]
        )

    top_score = max(ai_pct, df_pct)
    if low_min <= top_score <= low_max:
        return random.choice(
            [
                f"not sure on this one ({top_score:.0f}% AI generated/manipulated)",
                f"inconclusive. {top_score:.0f}% AI generated/manipulated.",
            ]
        )

    real_conf = (1 - ai_score) * 100
    return random.choice(
        [
            f"looks real to me ({real_conf:.0f}% sure)",
            f"it's not AI. {real_conf:.0f}% confident.",
            f"real. {real_conf:.0f}%.",
        ]
    )
