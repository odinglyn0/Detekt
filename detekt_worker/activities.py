import asyncio
from dataclasses import dataclass

from temporalio import activity
import structlog

from utils.secrets import get_secret
from utils.tiktok import (
    create_api_session,
    close_api_session,
    poll_mentions,
    is_supported_aweme,
    determine_type,
    get_video_info,
    extract_video_download_url,
    extract_slideshow_image_urls,
    reply_sync,
)
from utils.storage import (
    upload_video,
    upload_slideshow_images,
    get_signed_url,
    get_video_blob_path,
    get_photo_blob_path,
)
from utils.sightengine import check_image, check_video, format_result
from utils.firestore import get_cached_result, store_scan_result
from utils.rate_limiter import is_rate_limited

logger = structlog.get_logger()


@dataclass
class MentionData:
    comment_id: str
    aweme_id: str
    username: str
    aweme_type: int | None
    message: str


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
    try:
        await create_api_session()
    except Exception as exc:
        await close_api_session()
        raise exc

    try:
        mentions = await poll_mentions()
    except Exception as exc:
        await close_api_session()
        raise exc

    if not mentions:
        await close_api_session()
        return []

    trigger_word = get_secret("DTKT_TRIGGER_WORD").lower()
    blacklist_raw = get_secret("DTKT_USER_BLACKLIST")
    blacklist = {u.strip().lower() for u in blacklist_raw.split(",") if u.strip()}

    results = []
    for n in mentions:
        cid = str(getattr(n, "comment_id", "") or "")
        if not cid:
            continue

        vid = str(getattr(n, "aweme_id", "") or "")
        username = getattr(n.user, "unique_id", "unknown") if hasattr(n, "user") else "unknown"
        aweme_type = getattr(n, "aweme_type", None)
        message = getattr(n, "text", "") or getattr(n, "comment_text", "") or ""

        if not vid:
            continue

        if trigger_word not in message.lower():
            continue

        if username.lower() in blacklist:
            logger.info("dtkt-blacklisted-user", vid=vid, user=username)
            continue

        if aweme_type is not None and not is_supported_aweme(aweme_type):
            logger.info("dtkt-unsupported-type", vid=vid, type=aweme_type)
            continue

        results.append(MentionData(
            comment_id=cid,
            aweme_id=vid,
            username=username,
            aweme_type=aweme_type,
            message=message,
        ))

    await close_api_session()
    return results


@activity.defn
async def validate_and_download_media(mention: MentionData) -> ScanRequest | None:
    try:
        await create_api_session()
    except Exception as exc:
        await close_api_session()
        raise exc

    try:
        aweme = await get_video_info(mention.aweme_id)
    except Exception as exc:
        await close_api_session()
        raise exc

    if not aweme:
        await close_api_session()
        return None

    if mention.aweme_type is None and not is_supported_aweme(aweme.get("aweme_type", -1)):
        logger.info("dtkt-unsupported-type", vid=mention.aweme_id, type=aweme.get("aweme_type"))
        await close_api_session()
        return None

    content_type = determine_type(aweme)

    logger.info(
        "dtkt-mention-found",
        vid=mention.aweme_id,
        cid=mention.comment_id,
        user=mention.username,
        content_type=content_type,
    )

    quantity = None
    try:
        if content_type == 1:
            dl_url = extract_video_download_url(aweme)
            if dl_url:
                upload_video(mention.aweme_id, dl_url)
        else:
            image_urls = extract_slideshow_image_urls(aweme)
            if image_urls:
                _, quantity = upload_slideshow_images(mention.aweme_id, image_urls)
            else:
                quantity = 0
    except Exception as exc:
        logger.warning("dtkt-media-download-error", vid=mention.aweme_id, error=str(exc))

    await close_api_session()

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

    if request.content_type == 0 and request.quantity is not None and request.quantity > 1:
        logger.info("dtkt-slideshow-skipped", vid=request.vid, q=request.quantity)
        return None

    if is_rate_limited(request.username):
        raise RuntimeError(f"rate limited: {request.username}")

    cached = get_cached_result(request.vid)
    if cached:
        return {
            "dtkt_ai_score": cached["dtkt_ai_score"],
            "dtkt_is_ai": cached["dtkt_is_ai"],
            "media_type": media_type,
        }

    if request.content_type == 1:
        blob_path = get_video_blob_path(request.vid)
        if not blob_path:
            logger.warning("dtkt-video-not-found-in-bucket", vid=request.vid)
            raise RuntimeError(f"video blob not found for {request.vid}")
        signed_url = get_signed_url(blob_path)
        scan = check_video(signed_url)
    else:
        blob_path = get_photo_blob_path(request.vid)
        if not blob_path:
            logger.warning("dtkt-photo-not-found-in-bucket", vid=request.vid)
            raise RuntimeError(f"photo blob not found for {request.vid}")
        signed_url = get_signed_url(blob_path)
        scan = check_image(signed_url)

    store_scan_result(
        media_id=request.vid,
        media_type=media_type,
        ai_score=scan["dtkt_ai_score"],
        is_ai=scan["dtkt_is_ai"],
        vid=request.vid,
        cid=request.cid,
        username=request.username,
        message=request.message,
        raw_response=scan["dtkt_raw"],
    )

    return {
        "dtkt_ai_score": scan["dtkt_ai_score"],
        "dtkt_is_ai": scan["dtkt_is_ai"],
        "media_type": media_type,
    }


@activity.defn
async def reply_with_result(request: ScanRequest, result: dict) -> None:
    result_text = format_result(
        tagger=request.username,
        media_type=result["media_type"],
        is_ai=result["dtkt_is_ai"],
        ai_score=result["dtkt_ai_score"],
    )
    try:
        reply_sync(request.vid, request.cid, request.username, result_text)
    except Exception as exc:
        logger.warning("dtkt-reply-error", vid=request.vid, error=str(exc))
    logger.info("dtkt-result-sent", vid=request.vid, result=result_text)
