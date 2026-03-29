from webshare import ApiClient
from secret_manager import get_secret
import random
import requests
import structlog

logger = structlog.get_logger()


def get_proxy() -> dict:
    api_key = get_secret("DTKT_WEBSHARE_API_KEY")
    country = get_secret("DTKT_WEBSHARE_COUNTRY")
    count = int(get_secret("DTKT_WEBSHARE_PROXY_COUNT"))

    client = ApiClient(api_key)
    config = client.get_proxy_config()
    idx = random.randint(1, count)
    username = f"{config.username}-{country.lower()}-{idx}"
    password = config.password

    logger.info("webshare-proxy-loaded", country=country, host="p.webshare.io", idx=idx)
    return {
        "server": "http://p.webshare.io:80",
        "username": username,
        "password": password,
    }


def get_proxy_url() -> str:
    p = get_proxy()
    return f"http://{p['username']}:{p['password']}@p.webshare.io:80"


def verify_proxy():
    url = get_proxy_url()
    logger.info("webshare-proxy-verify", url=url.split("@")[1])
    resp = requests.get("http://api.ipify.org/?format=json", proxies={"http": url, "https": url}, timeout=10)
    ip = resp.json().get("ip")
    logger.info("webshare-proxy-ip", ip=ip)
