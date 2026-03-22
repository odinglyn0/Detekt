import time

from upstash_redis import Redis
import structlog

from utils.secrets import get_secret

logger = structlog.get_logger()

_redis: Redis | None = None
_redis_url: str | None = None
_redis_token: str | None = None
_redis_last_check: float = 0

DTKT_REDIS_REFRESH_INTERVAL = 120


def _get_redis() -> Redis:
    global _redis, _redis_url, _redis_token, _redis_last_check

    now = time.monotonic()
    if _redis is not None and (now - _redis_last_check) < DTKT_REDIS_REFRESH_INTERVAL:
        return _redis

    dtkt_upstash_url = get_secret("DTKT_UPSTASH_REDIS_URL")
    dtkt_upstash_token = get_secret("DTKT_UPSTASH_REDIS_TOKEN")

    if (
        _redis is not None
        and dtkt_upstash_url == _redis_url
        and dtkt_upstash_token == _redis_token
    ):
        _redis_last_check = now
        return _redis

    _redis = Redis(url=dtkt_upstash_url, token=dtkt_upstash_token)
    _redis_url = dtkt_upstash_url
    _redis_token = dtkt_upstash_token
    _redis_last_check = now
    logger.info("dtkt-redis-init")
    return _redis


def is_rate_limited(username: str) -> bool:
    redis = _get_redis()
    rl_window = int(get_secret("DTKT_RATE_LIMIT_WINDOW"))
    rl_max = int(get_secret("DTKT_RATE_LIMIT_MAX"))
    key = f"dtkt-rl:{username}"

    current = redis.get(key)
    if current is not None and int(current) >= rl_max:
        logger.info("dtkt-rate-limited", user=username)
        return True

    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, rl_window)
    pipe.exec()

    return False
