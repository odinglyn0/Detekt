import random

import structlog

from utils.secrets import get_secret

logger = structlog.get_logger()

_proxy_list: list[str] | None = None


def _load_proxies() -> list[str]:
    global _proxy_list
    if _proxy_list is not None:
        return _proxy_list

    raw = get_secret("DTKT_PROXY_URLS")
    proxies = [p.strip() for p in raw.split(",") if p.strip()]

    if not proxies:
        logger.warning("dtkt-no-proxies-configured")
        _proxy_list = []
        return _proxy_list

    _proxy_list = proxies
    logger.info("dtkt-proxies-loaded", count=len(_proxy_list))
    return _proxy_list


def reload_proxies() -> None:
    global _proxy_list
    _proxy_list = None


def get_proxy() -> str | None:
    proxies = _load_proxies()
    if not proxies:
        return None
    return random.choice(proxies)


def get_httpx_proxy() -> str | None:
    return get_proxy()


def get_playwright_proxy() -> dict | None:
    url = get_proxy()
    if not url:
        return None
    return {"server": url}
