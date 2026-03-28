from temporalio.client import Client
from temporalio.worker import Worker
from config import TEMPORAL_ADDRESS, TEMPORAL_NAMESPACE, TEMPORAL_API_KEY, TASK_QUEUE
from workflows import ReplyWorkflow, do_reply
from log import logger


async def create_client() -> Client:
    return await Client.connect(
        TEMPORAL_ADDRESS,
        namespace=TEMPORAL_NAMESPACE,
        rpc_metadata={"temporal-namespace": TEMPORAL_NAMESPACE},
        api_key=TEMPORAL_API_KEY,
        tls=True,
    )


async def run_worker():
    client = await create_client()
    logger.info("temporal-connected", address=TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ReplyWorkflow],
        activities=[do_reply],
    )
    logger.info("worker-starting", task_queue=TASK_QUEUE)
    await worker.run()
