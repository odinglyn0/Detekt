import json

from google.oauth2 import service_account
import structlog

from utils.secrets import get_secret_optional

logger = structlog.get_logger()

_credentials: service_account.Credentials | None = None
_project_id: str | None = None


def _load_credentials() -> tuple[service_account.Credentials, str]:
    global _credentials, _project_id
    if _credentials is not None:
        return _credentials, _project_id

    sa_json = get_secret_optional("DTKT_GCP_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        logger.info("dtkt-gcp-creds-using-adc")
        return None, None

    info = json.loads(sa_json)
    _credentials = service_account.Credentials.from_service_account_info(info)
    _project_id = info.get("project_id")
    logger.info("dtkt-gcp-creds-loaded", project=_project_id)
    return _credentials, _project_id


def get_credentials() -> service_account.Credentials | None:
    creds, _ = _load_credentials()
    return creds


def get_project_id() -> str | None:
    _, project = _load_credentials()
    return project
