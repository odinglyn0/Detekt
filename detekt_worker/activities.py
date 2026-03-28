from dataclasses import dataclass
import asyncio

import sentry_sdk
from temporalio import activity
from temporalio.exceptions import ApplicationError
import structlog

from utils.secrets import get_secret
from utils.tiktok import (
    poll_mentions,
    is_supported_aweme,
    classify_aweme_type,
    get_video_info,
    extract_video_download_url,
    extract_slideshow_image_urls,
    reply_to_comment,
    recreate_session,
)
from utils.storage import (
    upload_video,
    upload_slideshow_images,
    get_signed_url,
    get_video_blob_path,
    get_photo_blob_path,
)
from utils.sightengine import check_image, check_video, format_result
from utils.firestore import get_cached_result, store_scan_result, is_mention_seen, mark_mention_seen, store_skipped
from utils.rate_limiter import is_rate_limited

logger = structlog.get_logger()


@activity.defn
async def get_poll_interval() -> int:
    return int(get_secret("DTKT_POLL_INTERVAL_SECONDS"))


@dataclass
class MentionData:
    comment_id: str
    aweme_id: str
    username: str
    aweme_type: int | None
    message: str
    media_type: str
    video_url: str | None = None
    image_urls: list[str] | None = None


@dataclass
class ScanRequest:
    vid: str
    cid: str
    username: str
    content_type: int
    message: str
    quantity: int | None


@activity.defn
async def poll_tiktok_mentions() -> list[MentionData]:
    mentions = await poll_mentions()

    if not mentions:
        return []

    trigger_word = get_secret("DTKT_TRIGGER_WORD").lower()
    blacklist_raw = get_secret("DTKT_USER_BLACKLIST")
    blacklist = {u.strip().lower() for u in blacklist_raw.split(",") if u.strip()}

    results = []
    for m in mentions:
        cid = str(m.get("comment_id", "") or "")
        vid = str(m.get("aweme_id", "") or "")
        username = m.get("username", "")
        aweme_type = m.get("aweme_type")
        message = m.get("comment_text", "")

        if not cid or not vid:
            continue

        if await is_mention_seen(cid):
            continue

        if trigger_word not in message.lower():
            continue

        if username.lower() in blacklist:
            logger.info("dtkt-blacklisted-user", vid=vid, user=username)
            await mark_mention_seen(cid, vid)
            continue

        if aweme_type is not None and not is_supported_aweme(aweme_type):
            logger.info("dtkt-unsupported-type", vid=vid, type=aweme_type)
            await store_skipped(vid, f"unsupported_type:{aweme_type}", cid=cid)
            continue

        await mark_mention_seen(cid, vid)

        results.append(
            MentionData(
                comment_id=cid,
                aweme_id=vid,
                username=username,
                aweme_type=aweme_type,
                message=message,
                media_type=m.get("media_type", "video"),
                video_url=m.get("video_url"),
                image_urls=m.get("image_urls"),
            )
        )

    return results


@activity.defn
async def validate_and_download_media(mention: MentionData) -> ScanRequest | None:
    classified = classify_aweme_type(mention.aweme_type)
    if classified == "unknown":
        content_type = 0 if mention.media_type == "slideshow" else 1
    else:
        content_type = 0 if classified == "slideshow" else 1

    logger.info(
        "dtkt-mention-found",
        vid=mention.aweme_id,
        cid=mention.comment_id,
        user=mention.username,
        content_type=content_type,
    )

    video_url = mention.video_url
    image_urls = mention.image_urls

    if content_type == 1 and not video_url:
        aweme = await get_video_info(mention.aweme_id)
        if aweme:
            video_url = extract_video_download_url(aweme)

    if content_type == 0 and not image_urls:
        aweme = await get_video_info(mention.aweme_id)
        if aweme:
            image_urls = extract_slideshow_image_urls(aweme)

    quantity = None
    try:
        if content_type == 1:
            if video_url:
                await upload_video(mention.aweme_id, video_url)
        else:
            if image_urls:
                _, quantity = await upload_slideshow_images(
                    mention.aweme_id, image_urls
                )
            else:
                quantity = 0
    except Exception as exc:
        logger.warning(
            "dtkt-media-download-error", vid=mention.aweme_id, error=str(exc)
        )

    return ScanRequest(
        vid=mention.aweme_id,
        cid=mention.comment_id,
        username=mention.username,
        content_type=content_type,
        message=mention.message,
        quantity=quantity,
    )


@activity.defn
async def scan_media(request: ScanRequest) -> dict | None:
    media_type = "video" if request.content_type == 1 else "photo"

    if request.content_type == 0 and request.quantity is not None:
        if request.quantity == 0:
            logger.warning(
                "dtkt-slideshow-no-images",
                vid=request.vid,
                msg="quantity is 0, media download may have failed",
            )
            return None
        if request.quantity > 1:
            logger.info("dtkt-slideshow-skipped", vid=request.vid, q=request.quantity)
            return None

    if await is_rate_limited(request.username):
        raise RuntimeError(f"rate limited: {request.username}")

    cached = await get_cached_result(request.vid)
    if cached:
        return {
            "dtkt_ai_score": cached["dtkt_ai_score"],
            "dtkt_is_ai": cached["dtkt_is_ai"],
            "dtkt_deepfake_score": cached.get("dtkt_deepfake_score", 0.0),
            "dtkt_is_deepfake": cached.get("dtkt_is_deepfake", False),
            "media_type": media_type,
        }

    if request.content_type == 1:
        blob_path = await get_video_blob_path(request.vid)
        if not blob_path:
            logger.warning("dtkt-video-not-found-in-bucket", vid=request.vid)
            raise ApplicationError(
                f"video blob not found for {request.vid}", non_retryable=True
            )
        signed_url = await get_signed_url(blob_path)
        scan = await asyncio.to_thread(check_video, signed_url)
    else:
        blob_path = await get_photo_blob_path(request.vid)
        if not blob_path:
            logger.warning("dtkt-photo-not-found-in-bucket", vid=request.vid)
            raise ApplicationError(
                f"photo blob not found for {request.vid}", non_retryable=True
            )
        signed_url = await get_signed_url(blob_path)
        scan = await asyncio.to_thread(check_image, signed_url)

    await store_scan_result(
        media_id=request.vid,
        media_type=media_type,
        ai_score=scan["dtkt_ai_score"],
        is_ai=scan["dtkt_is_ai"],
        deepfake_score=scan["dtkt_deepfake_score"],
        is_deepfake=scan["dtkt_is_deepfake"],
        vid=request.vid,
        cid=request.cid,
        username=request.username,
        message=request.message,
        raw_response=scan["dtkt_raw"],
    )

    return {
        "dtkt_ai_score": scan["dtkt_ai_score"],
        "dtkt_is_ai": scan["dtkt_is_ai"],
        "dtkt_deepfake_score": scan["dtkt_deepfake_score"],
        "dtkt_is_deepfake": scan["dtkt_is_deepfake"],
        "media_type": media_type,
    }


@activity.defn
async def reply_with_result(request: ScanRequest, result: dict) -> None:
    result_text = format_result(
        tagger=request.username,
        media_type=result["media_type"],
        is_ai=result["dtkt_is_ai"],
        ai_score=result["dtkt_ai_score"],
        is_deepfake=result["dtkt_is_deepfake"],
        deepfake_score=result["dtkt_deepfake_score"],
    )
    try:
        await reply_to_comment(request.vid, request.cid, request.username, result_text)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        sentry_sdk.flush(timeout=2)
        logger.warning("dtkt-reply-error", vid=request.vid, error=str(exc))
    logger.info("dtkt-result-sent", vid=request.vid, result=result_text)
