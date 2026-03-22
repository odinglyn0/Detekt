from upstash_redis import Redis
import structlog

from utils.secrets import get_secret

logger = structlog.get_logger()

_redis: Redis | None = None


def _get_redis() -> Redis:
    global _redis
    if _redis is not None:
        return _redis

    dtkt_upstash_url = get_secret("DTKT_UPSTASH_REDIS_URL")
    dtkt_upstash_token = get_secret("DTKT_UPSTASH_REDIS_TOKEN")

    _redis = Redis(url=dtkt_upstash_url, token=dtkt_upstash_token)
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
