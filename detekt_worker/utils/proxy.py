from __future__ import annotations

from urllib.parse import urlparse
from typing import List, Optional

import structlog
from proxyproviders import ProxyProvider, ProxyConfig
from proxyproviders.models.proxy import Proxy

from utils.secrets import get_secret

logger = structlog.get_logger()


class DopplerProxyProvider(ProxyProvider):
    def __init__(
        self,
        secret_key: str = "DTKT_PROXY_URLS",
        config: Optional[ProxyConfig] = None,
    ):
        self._secret_key = secret_key
        super().__init__(config=config)

    def _fetch_proxies(self) -> List[Proxy]:
        raw = get_secret(self._secret_key)
        urls = [u.strip() for u in raw.split(",") if u.strip()]

        proxies: List[Proxy] = []
        for idx, url in enumerate(urls):
            parsed = urlparse(url)
            proxy = Proxy(
                id=str(idx),
                username=parsed.username or "",
                password=parsed.password or "",
                proxy_address=parsed.hostname or "",
                port=parsed.port or 80,
                protocols=[parsed.scheme] if parsed.scheme else ["socks5"],
            )
            proxies.append(proxy)

        logger.info("dtkt-proxies-loaded", count=len(proxies))
        return proxies


_provider: DopplerProxyProvider | None = None


def get_proxy_provider() -> DopplerProxyProvider:
    global _provider
    if _provider is None:
        _provider = DopplerProxyProvider(
            config=ProxyConfig(refresh_interval=120),
        )
    return _provider
