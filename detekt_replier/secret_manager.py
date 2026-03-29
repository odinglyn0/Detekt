import json
import subprocess
import sys
import threading
import time

import structlog

logger = structlog.get_logger()

_cache: dict = {}
_cache_ts: float = 0
_lock = threading.Lock()

_DTKT_CACHE_TTL: int | None = None
_DTKT_REFRESH_INTERVAL: int | None = None


def _get_cache_ttl() -> int:
    global _DTKT_CACHE_TTL
    if _DTKT_CACHE_TTL is not None:
        return _DTKT_CACHE_TTL
    return 120


def _get_refresh_interval() -> int:
    global _DTKT_REFRESH_INTERVAL
    if _DTKT_REFRESH_INTERVAL is not None:
        return _DTKT_REFRESH_INTERVAL
    return 30


def _fetch_secrets() -> dict:
    try:
        result = subprocess.run(
            ["doppler", "secrets", "download", "--no-file", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        secrets = json.loads(result.stdout)
        logger.info("dtkt-secrets-refreshed", count=len(secrets))
        return secrets
    except subprocess.CalledProcessError as exc:
        logger.error("dtkt-secrets-failed", stderr=exc.stderr)
        return {}
    except subprocess.TimeoutExpired:
        logger.error("dtkt-secrets-timeout")
        return {}


def _refresh_loop() -> None:
    global _cache, _cache_ts
    while True:
        time.sleep(_get_refresh_interval())
        fresh = _fetch_secrets()
        if fresh:
            with _lock:
                _cache = fresh
                _cache_ts = time.monotonic()


def _ensure_loaded() -> dict:
    global _cache, _cache_ts
    with _lock:
        now = time.monotonic()
        if _cache and (now - _cache_ts) < _get_cache_ttl():
            return _cache

    fresh = _fetch_secrets()
    if not fresh:
        with _lock:
            if _cache:
                logger.warning("dtkt-secrets-stale-fallback")
                return _cache
        logger.error("dtkt-secrets-empty")
        sys.exit(1)

    with _lock:
        _cache = fresh
        _cache_ts = time.monotonic()
        return _cache


_refresh_thread: threading.Thread | None = None


def _start_refresh_thread() -> None:
    global _refresh_thread
    if _refresh_thread is not None:
        return
    _refresh_thread = threading.Thread(target=_refresh_loop, daemon=True)
    _refresh_thread.start()
    logger.info("dtkt-secrets-refresh-thread-started", interval=_get_refresh_interval())


def get_secret(key: str) -> str:
    _start_refresh_thread()
    secrets = _ensure_loaded()
    _update_tunables(secrets)
    value = secrets.get(key)
    if value is None:
        logger.error("dtkt-secret-missing", key=key)
        sys.exit(1)
    return value


def get_secret_optional(key: str, default: str = "") -> str:
    _start_refresh_thread()
    secrets = _ensure_loaded()
    _update_tunables(secrets)
    return secrets.get(key, default)


def _update_tunables(secrets: dict) -> None:
    global _DTKT_CACHE_TTL, _DTKT_REFRESH_INTERVAL
    if "DTKT_SECRETS_CACHE_TTL" in secrets:
        _DTKT_CACHE_TTL = int(secrets["DTKT_SECRETS_CACHE_TTL"])
    if "DTKT_SECRETS_REFRESH_INTERVAL" in secrets:
        _DTKT_REFRESH_INTERVAL = int(secrets["DTKT_SECRETS_REFRESH_INTERVAL"])
