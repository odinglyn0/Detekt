import asyncio
import base64
import time
from browser import (
    get_page,
    reboot_session,
    check_status8,
    needs_reboot,
    _lock,
    SessionRebootError,
)
from debug_screenshots import DebugScreenshots
from log import logger


def build_video_url(username: str, aweme_id: str, comment_id: str) -> str:
    cid_b64 = base64.b64encode(comment_id.encode()).decode().rstrip("=")
    return f"https://www.tiktok.com/@{username}/video/{aweme_id}?cid={cid_b64}"


async def reply_to_comment(
    aweme_id: str, comment_id: str, initiator: str, username: str, message: str
) -> bool:
    if needs_reboot():
        logger.info("pre-reply-reboot", aweme_id=aweme_id, comment_id=comment_id)
        await reboot_session()
        raise SessionRebootError("session rebooted before reply, retrying")

    got_status8 = False

    async with _lock:
        page = get_page()
        dbg = DebugScreenshots(page, prefix=f"{aweme_id}-{comment_id}")
        dbg.start()
        try:
            t0 = time.monotonic()
            url = build_video_url(username, aweme_id, comment_id)
            logger.info(
                "reply-start",
                aweme_id=aweme_id,
                comment_id=comment_id,
                initiator=initiator,
            )
            await page.route("**/*.{mp4,webm,m3u8,ts,m4s}", lambda route: route.abort())
            await page.route("**/*.{jpg,jpeg,png,gif,webp,svg,ico}", lambda route: route.abort())
            await page.route("**/*.{woff,woff2,ttf,otf,eot}", lambda route: route.abort())
            await page.route("**/*.css", lambda route: route.abort())
            await page.route("**/media/**", lambda route: route.abort())
            await page.route("**/analytics/**", lambda route: route.abort())
            await page.route("**/slardar/**", lambda route: route.abort())
            await page.route("**/mon/**", lambda route: route.abort())
            await page.route("**/log/**", lambda route: route.abort())
            await page.route("**/xgplayer/**", lambda route: route.abort())
            await page.route("**/secsdk/**", lambda route: route.abort())
            logger.info("reply-routes-set", elapsed=f"{time.monotonic()-t0:.2f}s")

            for attempt in range(3):
                t1 = time.monotonic()
                await page.goto(url, wait_until="domcontentloaded")
                logger.info("reply-page-goto-done", elapsed=f"{time.monotonic()-t1:.2f}s", attempt=attempt+1)

                t2 = time.monotonic()
                await asyncio.sleep(0.5)

                trouble = page.locator(
                    'text="We\'re having trouble playing this video"'
                )
                if await trouble.count() > 0:
                    logger.warning(
                        "video-load-failed", attempt=attempt + 1, aweme_id=aweme_id
                    )
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue
                    else:
                        raise Exception(
                            f"Video failed to load after 3 attempts: {aweme_id}"
                        )
                break

            t3 = time.monotonic()
            first_comment = page.locator(
                '[class*="DivCommentListContainer"] [class*="DivCommentObjectWrapper"]'
            ).first
            await first_comment.wait_for(state="visible", timeout=10000)
            logger.info("reply-comment-visible", elapsed=f"{time.monotonic()-t3:.2f}s")

            t4 = time.monotonic()
            reply_btn = first_comment.locator('[data-e2e="comment-reply-1"]')
            await reply_btn.dispatch_event("click")
            await asyncio.sleep(0.15)
            logger.info("reply-btn-clicked", elapsed=f"{time.monotonic()-t4:.2f}s")

            t5 = time.monotonic()
            editor = page.locator(
                '[data-e2e="comment-input"] [contenteditable="true"]'
            ).first
            await editor.wait_for(state="visible", timeout=5000)
            await editor.click(force=True)
            logger.info("reply-editor-ready", elapsed=f"{time.monotonic()-t5:.2f}s")

            t6 = time.monotonic()
            await page.keyboard.type(f"@{initiator}", delay=50)
            logger.info("reply-mention-typed", elapsed=f"{time.monotonic()-t6:.2f}s", chars=len(initiator)+1)

            await asyncio.sleep(0.5)

            t7 = time.monotonic()
            mention_item = page.locator('[data-e2e="comment-at-list"][data-index="0"]').first
            try:
                await mention_item.wait_for(state="visible", timeout=5000)
                logger.info("reply-popover-visible", elapsed=f"{time.monotonic()-t7:.2f}s")
                await mention_item.click(force=True)
                await asyncio.sleep(0.15)
                logger.info("mention-selected", initiator=initiator, aweme_id=aweme_id)
            except Exception as exc:
                logger.warning(
                    "mention-popover-failed",
                    initiator=initiator,
                    aweme_id=aweme_id,
                    elapsed=f"{time.monotonic()-t7:.2f}s",
                    error=str(exc),
                )
                await page.keyboard.type(" ", delay=5)

            t8 = time.monotonic()
            await page.keyboard.type(message, delay=5)
            logger.info("reply-message-typed", elapsed=f"{time.monotonic()-t8:.2f}s", chars=len(message))

            t9 = time.monotonic()
            publish_future = asyncio.get_running_loop().create_future()

            async def on_response(response):
                if "api/comment/publish" in response.url:
                    if not publish_future.done():
                        publish_future.set_result(True)

            page.on("response", on_response)

            post_btn = page.locator('[data-e2e="comment-post"]').first
            await post_btn.dispatch_event("click")
            logger.info("reply-post-btn-clicked", elapsed=f"{time.monotonic()-t9:.2f}s")

            try:
                await asyncio.wait_for(publish_future, timeout=15)
                logger.info("reply-publish-confirmed", elapsed=f"{time.monotonic()-t9:.2f}s")
            except asyncio.TimeoutError:
                page.remove_listener("response", on_response)
                logger.warning(
                    "publish-timeout", aweme_id=aweme_id, comment_id=comment_id,
                    elapsed=f"{time.monotonic()-t9:.2f}s",
                )
                return False

            page.remove_listener("response", on_response)
            got_status8 = check_status8()
            logger.info("reply-total-time", elapsed=f"{time.monotonic()-t0:.2f}s")
        finally:
            await page.unroute_all()
            await dbg.stop()

    if got_status8:
        logger.warning(
            "post-reply-status8-reboot", aweme_id=aweme_id, comment_id=comment_id
        )
        await reboot_session()
        raise SessionRebootError("status-8 during reply, retrying")

    logger.info("reply-done", aweme_id=aweme_id, comment_id=comment_id)
    return True
