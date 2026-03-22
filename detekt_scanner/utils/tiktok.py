import asyncio

from TikTokApi import TikTokApi
import structlog

from utils.secrets import get_secret

logger = structlog.get_logger()

_api: TikTokApi | None = None


async def _get_api() -> TikTokApi:
    global _api
    if _api is not None:
        return _api

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


async def reply_to_comment(vid: str, cid: str, username: str, result_text: str) -> None:
    api = await _get_api()
    text = f"@{username} - {result_text}"
    await api.comment.post(
        video_id=vid,
        text=text,
        reply_comment_id=cid,
    )
    logger.info("dtkt-reply-posted", vid=vid, cid=cid, text=text)


def reply_sync(vid: str, cid: str, username: str, result_text: str) -> None:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(reply_to_comment(vid, cid, username, result_text))
        else:
            loop.run_until_complete(reply_to_comment(vid, cid, username, result_text))
    except RuntimeError:
        asyncio.run(reply_to_comment(vid, cid, username, result_text))
