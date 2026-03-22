from TikTokApi import TikTokApi
import structlog

from utils.secrets import get_secret

logger = structlog.get_logger()

_api: TikTokApi | None = None


def _get_supported_types() -> set[int]:
    raw = get_secret("DTKT_SUPPORTED_TYPES")
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


async def create_api_session() -> TikTokApi:
    global _api
    ms_token = get_secret("DTKT_MS_TOKEN")

    _api = TikTokApi()
    await _api.create_sessions(
        ms_tokens=[ms_token],
        num_sessions=1,
        sleep_after=3,
        headless=True,
        browser="chromium",
        suppress_resource_load_types=["image", "media", "font", "stylesheet"],
    )
    logger.info("dtkt-tiktok-session-created")
    return _api


async def poll_mentions() -> list:
    if _api is None:
        raise RuntimeError("dtkt-session-not-initialized")

    notifications = await _api.user.notifications()
    return [n for n in notifications if getattr(n, "type", None) == "mention"]


def is_supported_aweme(aweme_type: int) -> bool:
    return aweme_type in _get_supported_types()


def determine_type(aweme: dict) -> int:
    aweme_type = aweme.get("aweme_type", aweme.get("type"))
    image_post = aweme.get("imagePost") or aweme.get("image_post_info")
    if image_post or aweme_type in {2, 68}:
        return 0
    return 1


async def get_video_info(video_id: str) -> dict | None:
    if _api is None:
        return None
    try:
        video = _api.video(id=video_id)
        return await video.info()
    except Exception as exc:
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
        thumbnail = img.get("thumbnail") or img.get("display_image") or img.get("owner_watermark_image") or {}
        url_list = thumbnail.get("url_list", [])
        if url_list:
            urls.append(url_list[0])

    return urls
