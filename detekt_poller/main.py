import asyncio
import signal
import sys

import structlog

from utils.secrets import get_secret
from utils.tiktok import (
    create_api_session,
    poll_mentions,
    is_supported_aweme,
    determine_type,
    get_video_info,
    extract_video_download_url,
    extract_slideshow_image_urls,
)
from utils.pubsub import publish_mention
from utils.storage import upload_video, upload_slideshow_images
from utils.state import is_comment_processed, mark_comment_processed, circuit_breaker_check

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger()

dtkt_running = True
_poll_lock = asyncio.Lock()


def _handle_signal(sig, frame):
    global dtkt_running
    logger.info("dtkt-shutdown-requested", signal=sig)
    dtkt_running = False


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


async def poll_cycle() -> None:
    async with _poll_lock:
        logger.info("dtkt-polling-mentions")

        try:
            mentions = await poll_mentions()

            if not mentions:
                logger.info("dtkt-no-new-mentions")
                return

            trigger_word = get_secret("DTKT_TRIGGER_WORD").lower()
            blacklist_raw = get_secret("DTKT_USER_BLACKLIST")
            blacklist = {u.strip().lower() for u in blacklist_raw.split(",") if u.strip()}

            for n in mentions:
                if not dtkt_running:
                    break

                cid = str(getattr(n, "comment_id", "") or "")
                if not cid:
                    continue

                if is_comment_processed(cid):
                    continue

                vid = str(getattr(n, "aweme_id", "") or "")
                username = getattr(n.user, "unique_id", "unknown") if hasattr(n, "user") else "unknown"
                aweme_type = getattr(n, "aweme_type", None)

                if not vid:
                    mark_comment_processed(cid, "", username)
                    continue

                if not circuit_breaker_check():
                    logger.warning("dtkt-circuit-breaker-active")
                    break

                message = getattr(n, "text", "") or getattr(n, "comment_text", "") or ""

                if trigger_word not in message.lower():
                    logger.info("dtkt-no-trigger", vid=vid, cid=cid)
                    mark_comment_processed(cid, vid, username)
                    continue

                if username.lower() in blacklist:
                    logger.info("dtkt-blacklisted-user", vid=vid, user=username)
                    mark_comment_processed(cid, vid, username)
                    continue

                if aweme_type is not None and not is_supported_aweme(aweme_type):
                    logger.info("dtkt-unsupported-type", vid=vid, type=aweme_type)
                    mark_comment_processed(cid, vid, username)
                    continue

                aweme = await get_video_info(vid)
                if not aweme:
                    mark_comment_processed(cid, vid, username)
                    continue

                if aweme_type is None and not is_supported_aweme(aweme.get("aweme_type", -1)):
                    logger.info("dtkt-unsupported-type", vid=vid, type=aweme.get("aweme_type"))
                    mark_comment_processed(cid, vid, username)
                    continue

                content_type = determine_type(aweme)

                logger.info(
                    "dtkt-mention-found",
                    vid=vid,
                    cid=cid,
                    user=username,
                    content_type=content_type,
                )

                quantity = None
                try:
                    if content_type == 1:
                        dl_url = extract_video_download_url(aweme)
                        if dl_url:
                            upload_video(vid, dl_url)
                    else:
                        image_urls = extract_slideshow_image_urls(aweme)
                        if image_urls:
                            _, quantity = upload_slideshow_images(vid, image_urls)
                        else:
                            quantity = 0
                except Exception as exc:
                    logger.warning("dtkt-media-download-error", vid=vid, error=str(exc))

                publish_mention(
                    vid=vid,
                    cid=cid,
                    username=username,
                    is_video=content_type,
                    message=message,
                    quantity=quantity,
                )

                mark_comment_processed(cid, vid, username)

        except Exception as exc:
            logger.warning("dtkt-poll-error", error=str(exc))


async def run() -> None:
    dtkt_poll_interval = int(get_secret("DTKT_POLL_INTERVAL_SECONDS"))

    logger.info("dtkt-poller-starting", interval=dtkt_poll_interval)

    api = None

    try:
        while dtkt_running:
            try:
                if api is None:
                    api = await create_api_session()

                await poll_cycle()

            except KeyboardInterrupt:
                break
            except Exception as exc:
                logger.error("dtkt-cycle-error", error=str(exc))
                if api is not None:
                    try:
                        await api.close_sessions()
                    except Exception:
                        pass
                    api = None

            if dtkt_running:
                logger.info("dtkt-sleeping", seconds=dtkt_poll_interval)
                await asyncio.sleep(dtkt_poll_interval)

    finally:
        if api is not None:
            try:
                await api.close_sessions()
            except Exception:
                pass
        logger.info("dtkt-poller-stopped")


if __name__ == "__main__":
    asyncio.run(run())
