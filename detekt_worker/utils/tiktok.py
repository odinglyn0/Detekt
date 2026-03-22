import asyncio
import json

import sentry_sdk
from TikTokApi import TikTokApi
import structlog

from proxyproviders.algorithms import Random

from utils.secrets import get_secret
from utils.proxy import get_proxy_provider

logger = structlog.get_logger()

_api: TikTokApi | None = None
_last_min_time: int = 0

MAX_SESSION_RETRIES = 2
SENTRY_FLUSH_TIMEOUT = 2


def _report(exc: Exception) -> None:
    sentry_sdk.capture_exception(exc)
    sentry_sdk.flush(timeout=SENTRY_FLUSH_TIMEOUT)


def _get_supported_types() -> set[int]:
    raw = get_secret("DTKT_SUPPORTED_TYPES")
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


async def ensure_session() -> TikTokApi:
    global _api
    if _api is not None:
        return _api

    try:
        _api = TikTokApi()
        await _api.create_sessions(
            ms_tokens=[get_secret("DTKT_MS_TOKEN")],
            num_sessions=1,
            sleep_after=3,
            headless=True,
            browser="webkit",
            suppress_resource_load_types=["image", "media", "font", "stylesheet"],
            proxy_provider=get_proxy_provider(),
            proxy_algorithm=Random(),
            cookies=[
                {
                    "name": "sessionid",
                    "value": get_secret("DTKT_TT_SESSIONID"),
                    "domain": ".tiktok.com",
                    "path": "/",
                },
                {
                    "name": "tt_csrf_token",
                    "value": get_secret("DTKT_TT_CSRF_TOKEN"),
                    "domain": ".tiktok.com",
                    "path": "/",
                },
                {
                    "name": "s_v_web_id",
                    "value": get_secret("DTKT_TT_S_V_WEB_ID"),
                    "domain": ".tiktok.com",
                    "path": "/",
                },
                {
                    "name": "msToken",
                    "value": get_secret("DTKT_MS_TOKEN"),
                    "domain": ".tiktok.com",
                    "path": "/",
                },
            ],
        )
    except Exception as exc:
        _api = None
        _report(exc)
        logger.error("dtkt-session-create-failed", error=str(exc))
        raise

    logger.info("dtkt-tiktok-session-created")
    return _api


async def recreate_session() -> TikTokApi:
    await close_session()
    return await ensure_session()


async def close_session() -> None:
    global _api
    if _api is not None:
        try:
            await _api.close_sessions()
        except Exception:
            pass
        _api = None
        logger.info("dtkt-tiktok-session-closed")


async def poll_mentions() -> list[dict]:
    global _last_min_time

    for attempt in range(MAX_SESSION_RETRIES + 1):
        api = await ensure_session()
        try:
            data = await api.make_request(
                url="https://www.tiktok.com/api/notice/multi/",
                params={
                    "aid": "1988",
                    "app_name": "tiktok_web",
                    "device_platform": "web_pc",
                    "group_list": json.dumps(
                        [
                            {
                                "count": 20,
                                "is_mark_read": 0,
                                "group": 500,
                                "max_time": 0,
                                "min_time": _last_min_time,
                            }
                        ]
                    ),
                },
            )
            break
        except Exception as exc:
            if attempt < MAX_SESSION_RETRIES:
                logger.warning(
                    "dtkt-poll-failed-retrying",
                    attempt=attempt + 1,
                    error=str(exc),
                )
                _report(exc)
                await recreate_session()
            else:
                _report(exc)
                logger.error("dtkt-poll-failed-exhausted", error=str(exc))
                return []

    mentions: list[dict] = []
    notice_lists = data.get("notice_lists", [])

    for group in notice_lists:
        for n in group.get("notice_list", []):
            if n.get("type") != 45:
                continue

            at = n.get("at", {})
            comment = at.get("comment", {})
            user_info = at.get("user_info", {})
            aweme = at.get("aweme", {})

            mention: dict = {
                "aweme_id": comment.get("aweme_id", ""),
                "comment_id": comment.get("cid", ""),
                "comment_text": at.get("content", ""),
                "username": user_info.get("unique_id", ""),
                "aweme_type": aweme.get("aweme_type"),
                "nid": n.get("nid", ""),
            }

            if aweme.get("image_post_info"):
                mention["media_type"] = "slideshow"
                mention["image_urls"] = [
                    img["display_image"]["url_list"][0]
                    for img in aweme["image_post_info"].get("images", [])
                    if img.get("display_image", {}).get("url_list")
                ]
            else:
                mention["media_type"] = "video"
                play_addr = aweme.get("video", {}).get("play_addr", {})
                url_list = play_addr.get("url_list", [])
                mention["video_url"] = url_list[0] if url_list else None

            mentions.append(mention)

    if notice_lists:
        new_max = notice_lists[0].get("max_time", 0)
        if new_max:
            _last_min_time = new_max

    logger.info("dtkt-poll-complete", count=len(mentions), min_time=_last_min_time)
    return mentions


def is_supported_aweme(aweme_type: int) -> bool:
    return aweme_type in _get_supported_types()


async def get_video_info(video_id: str) -> dict | None:
    for attempt in range(MAX_SESSION_RETRIES + 1):
        api = await ensure_session()
        try:
            video = api.video(id=video_id)
            return await video.info()
        except Exception as exc:
            if attempt < MAX_SESSION_RETRIES:
                logger.warning(
                    "dtkt-video-info-retrying",
                    vid=video_id,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                _report(exc)
                await recreate_session()
            else:
                _report(exc)
                logger.warning("dtkt-video-info-error", vid=video_id, error=str(exc))
                return None


def extract_video_download_url(aweme: dict) -> str | None:
    video = aweme.get("video", {})
    return (
        video.get("downloadAddr")
        or video.get("playAddr")
        or video.get("play_addr", {}).get("url_list", [None])[0]
    )


def extract_slideshow_image_urls(aweme: dict) -> list[str]:
    image_post = aweme.get("image_post_info") or aweme.get("imagePost") or {}
    images = image_post.get("images", [])
    urls = []
    for img in images:
        thumbnail = (
            img.get("thumbnail")
            or img.get("display_image")
            or img.get("owner_watermark_image")
            or {}
        )
        url_list = thumbnail.get("url_list", [])
        if url_list:
            urls.append(url_list[0])
    return urls


async def reply_to_comment(
    vid: str, cid: str, username: str, result_text: str, reply_type: str = "2"
) -> dict | None:
    safe_text = json.dumps(f"@{username} {result_text}")
    safe_vid = json.dumps(vid)
    safe_cid = json.dumps(cid)
    safe_reply_type = json.dumps(reply_type)

    for attempt in range(MAX_SESSION_RETRIES + 1):
        api = await ensure_session()
        try:
            result = await api._sessions[0].page.evaluate(
                f"""async () => {{
                    const body = new URLSearchParams({{
                        aweme_id: {safe_vid},
                        text: {safe_text},
                        reply_id: {safe_cid},
                        reply_type: {safe_reply_type}
                    }});
                    const response = await fetch(
                        "https://www.tiktok.com/api/comment/publish/",
                        {{ method: "POST", body: body }}
                    );
                    return await response.json();
                }}"""
            )
            logger.info("dtkt-reply-posted", vid=vid, cid=cid, result=result)
            return result
        except Exception as exc:
            if attempt < MAX_SESSION_RETRIES:
                logger.warning(
                    "dtkt-reply-retrying",
                    vid=vid,
                    cid=cid,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                _report(exc)
                await recreate_session()
            else:
                _report(exc)
                logger.error("dtkt-reply-failed", vid=vid, cid=cid, error=str(exc))
                return None
