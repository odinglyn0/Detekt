import asyncio
import os
import signal

import sentry_sdk
import structlog
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.worker import Worker

from workflows import PollerWorkflow, ProcessMentionWorkflow
from activities import (
    poll_tiktok_mentions,
    validate_and_download_media,
    scan_media,
    reply_with_result,
    get_poll_interval,
)
from utils.secrets import get_secret

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger()

DTKT_TASK_QUEUE = "dtkt-task-queue"


def _init_sentry() -> None:
    dsn = get_secret("DTKT_SENTRY_DSN")
    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=1.0,
        environment="production",
        enable_tracing=True,
    )
    logger.info("dtkt-sentry-initialized")


async def run() -> None:
    _init_sentry()

    temporal_host = os.environ["DTKT_TEMPORAL_HOST"]
    temporal_namespace = os.environ.get("DTKT_TEMPORAL_NAMESPACE", "default")
    temporal_api_key = os.environ.get("DTKT_TEMPORAL_API_KEY", "")
    poll_interval = int(get_secret("DTKT_POLL_INTERVAL_SECONDS"))

    logger.info(
        "dtkt-worker-connecting", host=temporal_host, namespace=temporal_namespace
    )

    connect_kwargs = {
        "target_host": temporal_host,
        "namespace": temporal_namespace,
    }
    if temporal_api_key:
        connect_kwargs["api_key"] = temporal_api_key
        connect_kwargs["tls"] = True

    client = await Client.connect(**connect_kwargs)

    logger.info("dtkt-worker-connected")

    worker = Worker(
        client,
        task_queue=DTKT_TASK_QUEUE,
        workflows=[PollerWorkflow, ProcessMentionWorkflow],
        activities=[
            poll_tiktok_mentions,
            validate_and_download_media,
            scan_media,
            reply_with_result,
            get_poll_interval,
        ],
    )

    shutdown_event = asyncio.Event()

    def _handle_signal():
        logger.info("dtkt-shutdown-requested")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    async with worker:
        logger.info("dtkt-worker-started", task_queue=DTKT_TASK_QUEUE)

        try:
            handle = client.get_workflow_handle("dtkt-poller")
            desc = await handle.describe()
            if desc.status == WorkflowExecutionStatus.RUNNING:
                logger.info("dtkt-poller-workflow-already-running")
            else:
                raise RuntimeError("not running")
        except Exception:
            await client.start_workflow(
                PollerWorkflow.run,
                poll_interval,
                id="dtkt-poller",
                task_queue=DTKT_TASK_QUEUE,
                id_conflict_policy=WorkflowIDConflictPolicy.TERMINATE_EXISTING,
            )
            logger.info("dtkt-poller-workflow-started", interval=poll_interval)

        await shutdown_event.wait()

    logger.info("dtkt-worker-stopped")


if __name__ == "__main__":
    asyncio.run(run())
