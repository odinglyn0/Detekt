import asyncio
import time
import sentry_sdk
from browserforge.fingerprints import Screen
from camoufox.async_api import AsyncCamoufox
from cookies import load_cookies
from log import logger

SESSION_TTL = 12 * 60 * 60

_browser = None
_context = None
_page = None
_camoufox_cm = None
_started_at: float = 0
_lock = asyncio.Lock()
_reboot_in_progress = False
_rotation_task = None
_status8_detected = False


class SessionRebootError(Exception):
    pass


async def _boot():
    global _browser, _context, _page, _camoufox_cm, _started_at, _status8_detected
    _status8_detected = False
    _camoufox_cm = AsyncCamoufox(
        headless="virtual",
        humanize=True,
        geoip=True,
        screen=Screen(min_width=1920, min_height=1000, max_width=2100, max_height=1100),
        window=(1920, 1080),
    )
    _browser = await _camoufox_cm.__aenter__()
    _context = (
        _browser.contexts[0] if _browser.contexts else await _browser.new_context()
    )
    cookies = load_cookies()
    await _context.add_cookies(cookies)
    _page = await _context.new_page()
    _attach_status8_listener(_page)
    await _page.goto("https://www.tiktok.com/explore")
    await _page.wait_for_load_state("load")
    _started_at = time.monotonic()
    logger.info("camoufox-booted")


async def _teardown():
    global _browser, _context, _page, _camoufox_cm
    if _camoufox_cm:
        try:
            await _camoufox_cm.__aexit__(None, None, None)
        except Exception:
            pass
    _browser = None
    _context = None
    _page = None
    _camoufox_cm = None


def _attach_status8_listener(page):
    async def _on_response(response):
        global _status8_detected
        if response.request.method == "POST" and response.status == 8:
            _status8_detected = True
            logger.warning("status-8-detected", url=response.url)
            sentry_sdk.capture_message(
                f"status-8 detected on POST {response.url}",
                level="warning",
            )

    page.on("response", _on_response)


async def reboot_session():
    global _reboot_in_progress
    async with _lock:
        _reboot_in_progress = True
        try:
            logger.info("camoufox-reboot-start")
            sentry_sdk.capture_message("camoufox session reboot", level="info")
            await _teardown()
            await _boot()
            logger.info("camoufox-reboot-done")
        finally:
            _reboot_in_progress = False


def get_page():
    return _page


def needs_reboot() -> bool:
    if _status8_detected:
        return True
    if _started_at and (time.monotonic() - _started_at) >= SESSION_TTL:
        return True
    return False


def check_status8() -> bool:
    return _status8_detected


async def _rotation_loop():
    while True:
        await asyncio.sleep(60)
        if _started_at and (time.monotonic() - _started_at) >= SESSION_TTL:
            await reboot_session()


async def init_browser():
    global _rotation_task
    async with _lock:
        await _boot()
    _rotation_task = asyncio.create_task(_rotation_loop())


async def shutdown_browser():
    global _rotation_task
    if _rotation_task:
        _rotation_task.cancel()
        try:
            await _rotation_task
        except asyncio.CancelledError:
            pass
        _rotation_task = None
    await _teardown()
