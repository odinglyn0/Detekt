import asyncio
import base64
from browser import get_page, reboot_session, check_status8, needs_reboot, _lock, SessionRebootError
from debug_screenshots import DebugScreenshots
from log import logger


def build_video_url(username: str, aweme_id: str, comment_id: str) -> str:
    cid_b64 = base64.b64encode(comment_id.encode()).decode()
    return f"https://www.tiktok.com/@{username}/video/{aweme_id}?cid={cid_b64}"


async def reply_to_comment(aweme_id: str, comment_id: str, initiator: str, username: str, message: str) -> bool:
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
            url = build_video_url(username, aweme_id, comment_id)
            logger.info("reply-start", aweme_id=aweme_id, comment_id=comment_id, initiator=initiator)

            for attempt in range(3):
                await page.goto(url)
                await page.wait_for_load_state("load")
                await asyncio.sleep(3)

                trouble = page.locator('text="We\'re having trouble playing this video"')
                if await trouble.count() > 0:
                    logger.warning("video-load-failed", attempt=attempt + 1, aweme_id=aweme_id)
                    if attempt < 2:
                        await asyncio.sleep(2)
                        continue
                    else:
                        raise Exception(f"Video failed to load after 3 attempts: {aweme_id}")
                break

            # Wait for the comment list (auto-opened by ?cid= param)
            comment_list = page.locator('[class*="DivCommentListContainer"]')
            await comment_list.wait_for(state="visible", timeout=15000)

            # First actual comment — use the content container with data-comment-ui-enabled
            first_comment = page.locator('[data-comment-ui-enabled="true"]').first
            await first_comment.wait_for(state="visible", timeout=15000)

            # Click Reply
            reply_btn = first_comment.locator('[data-e2e="comment-reply-1"]')
            await reply_btn.scroll_into_view_if_needed()
            await reply_btn.click()
            await asyncio.sleep(1)

            # After clicking reply, a new editor appears in the reply container
            reply_editor = page.locator('[class*="DivReplyContainer"] [contenteditable="true"]').first
            await reply_editor.wait_for(state="visible", timeout=10000)
            await reply_editor.click()
            await page.keyboard.type(message, delay=50)
            await asyncio.sleep(0.5)

            publish_future = asyncio.get_running_loop().create_future()

            async def on_response(response):
                if "api/comment/publish" in response.url:
                    if not publish_future.done():
                        publish_future.set_result(True)

            page.on("response", on_response)

            post_btn = page.locator('[data-e2e="comment-post"]')
            await post_btn.click()

            try:
                await asyncio.wait_for(publish_future, timeout=30)
            except asyncio.TimeoutError:
                page.remove_listener("response", on_response)
                logger.warning("publish-timeout", aweme_id=aweme_id, comment_id=comment_id)
                return False

            page.remove_listener("response", on_response)
            got_status8 = check_status8()

            if not got_status8:
                await page.goto("https://www.tiktok.com/explore")
                await page.wait_for_load_state("load")
        finally:
            await dbg.stop()

    if got_status8:
        logger.warning("post-reply-status8-reboot", aweme_id=aweme_id, comment_id=comment_id)
        await reboot_session()
        raise SessionRebootError("status-8 during reply, retrying")

    logger.info("reply-done", aweme_id=aweme_id, comment_id=comment_id)
    return True
