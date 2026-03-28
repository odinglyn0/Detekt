from dataclasses import dataclass
from datetime import timedelta
from temporalio import workflow, activity
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from tiktok import reply_to_comment
    from browser import SessionRebootError


@dataclass
class ReplyInput:
    aweme_id: str
    comment_id: str
    initiator: str
    message: str
    username: str


@activity.defn
async def do_reply(input: ReplyInput) -> bool:
    return await reply_to_comment(
        aweme_id=input.aweme_id,
        comment_id=input.comment_id,
        initiator=input.initiator,
        username=input.username,
        message=input.message,
    )


@workflow.defn(name="dtkt-reply")
class ReplyWorkflow:
    @workflow.run
    async def run(self, input: ReplyInput) -> bool:
        return await workflow.execute_activity(
            do_reply,
            input,
            start_to_close_timeout=timedelta(seconds=180),
            retry_policy=RetryPolicy(
                maximum_attempts=1,
            ),
        )
