from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy

with workflow.unsafe.imports_passed_through():
    from activities import (
        MentionData,
        ScanRequest,
        poll_tiktok_mentions,
        validate_and_download_media,
        scan_media,
        reply_with_result,
        get_poll_interval,
    )

DTKT_MAX_POLLS_BEFORE_CAN = 50


@workflow.defn
class ProcessMentionWorkflow:
    @workflow.run
    async def run(self, mention: MentionData) -> None:
        scan_request = await workflow.execute_activity(
            validate_and_download_media,
            mention,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=2),
                maximum_attempts=3,
            ),
        )

        if scan_request is None:
            return

        result = await workflow.execute_activity(
            scan_media,
            scan_request,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=10),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=5),
                maximum_attempts=5,
            ),
        )

        if result is None:
            return

        await workflow.execute_activity(
            reply_with_result,
            args=[scan_request, result],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=1),
                maximum_attempts=5,
            ),
        )


@workflow.defn
class PollerWorkflow:
    @workflow.run
    async def run(self, poll_interval_seconds: int) -> None:
        for _ in range(DTKT_MAX_POLLS_BEFORE_CAN):
            mentions = await workflow.execute_activity(
                poll_tiktok_mentions,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=10),
                    backoff_coefficient=2.0,
                    maximum_interval=timedelta(minutes=2),
                    maximum_attempts=3,
                ),
            )

            for mention in mentions:
                await workflow.start_child_workflow(
                    ProcessMentionWorkflow.run,
                    mention,
                    id=f"dtkt-mention-{mention.aweme_id}-{mention.comment_id}",
                    id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                )

            await workflow.sleep(timedelta(seconds=poll_interval_seconds))

        fresh_interval = await workflow.execute_activity(
            get_poll_interval,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                maximum_attempts=2,
            ),
        )

        workflow.continue_as_new(fresh_interval)
