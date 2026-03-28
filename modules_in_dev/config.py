from secret_manager import get_secret, get_secret_optional

TEMPORAL_ADDRESS = get_secret("DTKT_TEMPORAL_HOST")
TEMPORAL_NAMESPACE = get_secret("DTKT_TEMPORAL_NAMESPACE")
TEMPORAL_API_KEY = get_secret("DTKT_TEMPORAL_API_KEY")
TASK_QUEUE = get_secret("DTKT_TEMPORAL_TASK_QUEUE")
GCS_BUCKET = get_secret("DTKT_BUCKET_NAME")
GCS_COOKIES_PATH = get_secret("DTKT_GCS_COOKIES_PATH")
SENTRY_DSN = get_secret("DTKT_SENTRY_DSN")
GCP_SERVICE_ACCOUNT_JSON = get_secret("DTKT_GCP_SERVICE_ACCOUNT_JSON")
DBG_ENABLED = get_secret_optional("DTKT_DBG_ENA").lower()
GCS_DBG_SC_PATH = get_secret_optional("DTKT_GCS_DBGSC_PATH", "")
