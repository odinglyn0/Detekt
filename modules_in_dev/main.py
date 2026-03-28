import asyncio
import sentry_sdk
from config import SENTRY_DSN
from log import logger
from browser import init_browser, shutdown_browser
from worker import run_worker

sentry_sdk.init(
    dsn=SENTRY_DSN,
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    enable_tracing=True,
)


async def main():
    logger.info("dtkt-reply-worker-starting")
    await init_browser()
    try:
        await run_worker()
    finally:
        await shutdown_browser()
        logger.info("dtkt-reply-worker-stopped")


if __name__ == "__main__":
    asyncio.run(main())
