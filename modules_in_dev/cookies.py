import json
from google.cloud import storage
from google.oauth2 import service_account
from config import GCS_BUCKET, GCS_COOKIES_PATH, GCP_SERVICE_ACCOUNT_JSON
from log import logger


def _gcs_client() -> storage.Client:
    info = json.loads(GCP_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info)
    return storage.Client(credentials=creds, project=info.get("project_id"))


def download_cookies() -> str:
    client = _gcs_client()
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(GCS_COOKIES_PATH)
    content = blob.download_as_text()
    return content


def parse_netscape_cookies(raw: str) -> list[dict]:
    cookies = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _, path, secure, expires, name, value = parts[:7]
        cookies.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
            "secure": secure.upper() == "TRUE",
            "expires": int(expires) if int(expires) > 0 else -1,
        })
    return cookies


def load_cookies() -> list[dict]:
    raw = download_cookies()
    cookies = parse_netscape_cookies(raw)
    logger.info("cookies-loaded", count=len(cookies))
    return cookies
