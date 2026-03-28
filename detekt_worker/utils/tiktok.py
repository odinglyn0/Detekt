import asyncio
import json
import time

import sentry_sdk
from TikTokApi import TikTokApi
import structlog

from proxyproviders.algorithms import Random

from utils.secrets import get_secret
from utils.proxy import get_proxy_provider

logger = structlog.get_logger()

_api: TikTokApi | None = None
_last_min_time: int = 0
_session_created_at: float = 0

MAX_SESSION_RETRIES = 2
SENTRY_FLUSH_TIMEOUT = 2
SESSION_MAX_AGE_SECONDS = 45 * 60


def _report(exc: Exception) -> None:
    sentry_sdk.capture_exception(exc)
    sentry_sdk.flush(timeout=SENTRY_FLUSH_TIMEOUT)


VIDEO_AWEME_TYPES = {0, 4, 51, 55, 58, 61}
PHOTO_AWEME_TYPES = {2, 68, 150}


def classify_aweme_type(aweme_type: int | None) -> str:
    if aweme_type is None:
        return "unknown"
    if aweme_type in PHOTO_AWEME_TYPES:
        return "slideshow"
    if aweme_type in VIDEO_AWEME_TYPES:
        return "video"
    return "unknown"


def _get_supported_types() -> set[int]:
    raw = get_secret("DTKT_SUPPORTED_TYPES")
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


async def _extract_ms_token(api: TikTokApi) -> str | None:
    try:
        for session in api.sessions:
            cookies = await session.context.cookies()
            for cookie in cookies:
                if cookie.get("name") == "msToken" and cookie.get("value"):
                    return cookie["value"]
    except Exception as exc:
        logger.warning("dtkt-ms-token-extract-failed", error=str(exc))
    return None


async def ensure_session(force_fresh: bool = False) -> TikTokApi:
    global _api, _session_created_at

    if _api is not None and not force_fresh:
        age = time.monotonic() - _session_created_at
        if age < SESSION_MAX_AGE_SECONDS:
            return _api
        logger.info("dtkt-session-stale-rotating", age_seconds=int(age))
        await close_session()

    last_exc = None
    for attempt in range(1, MAX_SESSION_RETRIES + 1):
        try:
            _api = TikTokApi()

            async def _page_factory(context):
                await context.add_cookies(
                    [
                        {
                            "name": "sessionid",
                            "value": get_secret("DTKT_TT_SESSIONID"),
                            "domain": ".tiktok.com",
                            "path": "/",
                            "secure": True,
                            "httpOnly": True,
                            "sameSite": "None",
                        }
                    ]
                )
                page = await context.new_page()
                await page.goto("https://www.tiktok.com", wait_until="domcontentloaded")
                for _ in range(20):
                    cookies = await context.cookies()
                    if any(c["name"] == "msToken" and c.get("value") for c in cookies):
                        break
                    await asyncio.sleep(0.5)
                return page

            await _api.create_sessions(
                num_sessions=1,
                sleep_after=3,
                browser="chromium",
                headless=True,
                page_factory=_page_factory,
            )
            _session_created_at = time.monotonic()
            token = await _extract_ms_token(_api)
            logger.info(
                "dtkt-tiktok-session-created",
                has_token=token is not None,
                attempt=attempt,
            )
            return _api
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "dtkt-session-create-retry",
                attempt=attempt,
                max_attempts=MAX_SESSION_RETRIES,
                error=str(exc),
            )
            if _api is not None:
                try:
                    await _api.close_sessions()
                except Exception:
                    pass
                try:
                    await _api.stop_playwright()
                except Exception:
                    pass
                _api = None

            if attempt < MAX_SESSION_RETRIES:
                backoff = min(5 * attempt, 30)
                await asyncio.sleep(backoff)

    _report(last_exc)
    logger.error(
        "dtkt-session-create-failed-all-attempts", attempts=MAX_SESSION_RETRIES
    )
    raise last_exc


async def recreate_session() -> TikTokApi:
    return await ensure_session(force_fresh=True)


async def close_session() -> None:
    global _api
    if _api is not None:
        try:
            await _api.close_sessions()
        except Exception:
            pass
        try:
            await _api.stop_playwright()
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
            status = data.get("status_code", 0)
            if status in (3102, 3006, 8):
                if attempt < MAX_SESSION_RETRIES:
                    logger.warning(
                        "dtkt-login-expired-retrying",
                        status=status,
                        attempt=attempt + 1,
                    )
                    await recreate_session()
                    continue
                else:
                    logger.error("dtkt-login-expired-exhausted", status=status)
                    return []
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
            author = aweme.get("author", {})
            mention: dict = {
                "aweme_id": comment.get("aweme_id", ""),
                "comment_id": comment.get("cid", ""),
                "comment_text": at.get("content", ""),
                "username": user_info.get("unique_id", ""),
                "video_owner": author.get("unique_id", ""),
                "aweme_type": aweme.get("aweme_type"),
                "nid": n.get("nid", ""),
            }

            aweme_type_val = aweme.get("aweme_type")
            classified = classify_aweme_type(aweme_type_val)

            if classified == "slideshow" or (
                classified == "unknown"
                and (aweme.get("image_post_info") or aweme.get("imagePost"))
            ):
                mention["media_type"] = "slideshow"
                image_post = (
                    aweme.get("image_post_info") or aweme.get("imagePost") or {}
                )
                mention["image_urls"] = []
                images = image_post.get("images", [])
                if images:
                    logger.info(
                        "dtkt-slideshow-raw-sample",
                        vid=mention["aweme_id"],
                        image_keys=list(images[0].keys()) if images else [],
                        sample=str(images[0])[:500] if images else "empty",
                    )
                for img in images:
                    url = _extract_image_url(img)
                    if url:
                        mention["image_urls"].append(url)
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
            url = f"https://www.tiktok.com/@_/video/{video_id}"
            video = api.video(url=url)
            data = await video.info()
            if data:
                logger.info(
                    "dtkt-video-info-fetched",
                    vid=video_id,
                    top_keys=sorted(data.keys())[:15],
                    has_image_post_info="image_post_info" in data,
                    has_imagePost="imagePost" in data,
                )
            return data
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


def _pick_url(url_list: list) -> str | None:
    for item in url_list:
        if isinstance(item, str) and item:
            return item
        if isinstance(item, dict):
            val = item.get("url") or item.get("src") or item.get("uri") or ""
            if val:
                return val
    return None


def extract_video_download_url(aweme: dict) -> str | None:
    video = aweme.get("video", {})
    url = video.get("downloadAddr") or video.get("playAddr")
    if url and isinstance(url, str):
        return url
    if isinstance(video.get("playAddr"), list):
        for item in video["playAddr"]:
            if isinstance(item, dict) and item.get("src"):
                return item["src"]
    return _pick_url(video.get("download_addr", {}).get("url_list", [])) or _pick_url(
        video.get("play_addr", {}).get("url_list", [])
    )


def _extract_image_url(img: dict) -> str | None:
    for key in ("imageURL", "thumbnail", "display_image", "owner_watermark_image"):
        container = img.get(key)
        if not container or not isinstance(container, dict):
            continue
        url_list = container.get("urlList") or container.get("url_list") or []
        url = _pick_url(url_list)
        if url:
            return url
    url_list = img.get("urlList") or img.get("url_list") or []
    return _pick_url(url_list)


def extract_slideshow_image_urls(aweme: dict) -> list[str]:
    image_post = aweme.get("image_post_info") or aweme.get("imagePost") or {}
    images = image_post.get("images", [])
    urls = []
    for img in images:
        url = _extract_image_url(img)
        if url:
            urls.append(url)
    if not urls:
        logger.warning(
            "dtkt-slideshow-no-urls-extracted",
            keys=list(image_post.keys()) if image_post else [],
            image_count=len(images),
            sample_keys=list(images[0].keys()) if images else [],
        )
    return urls
