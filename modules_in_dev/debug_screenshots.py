import asyncio
import json
from google.cloud import storage
from google.oauth2 import service_account
from config import GCS_BUCKET, GCP_SERVICE_ACCOUNT_JSON, DBG_ENABLED, GCS_DBG_SC_PATH
from log import logger


def _gcs_client() -> storage.Client:
    info = json.loads(GCP_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info)
    return storage.Client(credentials=creds, project=info.get("project_id"))


class DebugScreenshots:
    def __init__(self, page, prefix: str = ""):
        self._page = page
        self._prefix = prefix
        self._task: asyncio.Task | None = None
        self._counter = 0

    async def _capture_loop(self):
        client = _gcs_client()
        bucket = client.bucket(GCS_BUCKET)
        try:
            while True:
                self._counter += 1
                filename = f"{self._counter}.png"
                gcs_path = f"{GCS_DBG_SC_PATH}/{self._prefix}/{filename}".replace("//", "/")
                try:
                    screenshot = await self._page.screenshot(type="png")
                    blob = bucket.blob(gcs_path)
                    blob.upload_from_string(screenshot, content_type="image/png")
                except Exception as exc:
                    logger.warning("dbg-screenshot-failed", error=str(exc), counter=self._counter)
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    def start(self):
        if not DBG_ENABLED or not GCS_DBG_SC_PATH:
            return
        logger.info("dbg-screenshots-start", prefix=self._prefix)
        self._task = asyncio.create_task(self._capture_loop())

    async def stop(self):
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("dbg-screenshots-stop", prefix=self._prefix, count=self._counter)
