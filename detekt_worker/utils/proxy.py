from webshare import ApiClient
from utils.secrets import get_secret
import random
import requests
import structlog

logger = structlog.get_logger()

_HOST = "p.webshare.io"
_PORT = 80


def get_proxy() -> dict:
    api_key = get_secret("DTKT_WEBSHARE_API_KEY")
    country = get_secret("DTKT_WEBSHARE_COUNTRY")

    client = ApiClient(api_key)
    config = client.get_proxy_config()
    proxies = client.get_proxy_list(mode="backbone", country_code_in=country)
    count = proxies.count
    idx = random.randint(1, max(count, 1))
    username = f"{config.username}-{country.lower()}-{idx}"
    password = config.password

    logger.info("webshare-proxy-loaded", country=country, host=_HOST)
    return {
        "server": f"http://{_HOST}:{_PORT}",
        "username": username,
        "password": password,
    }


def get_proxy_url() -> str:
    p = get_proxy()
    return f"http://{p['username']}:{p['password']}@{_HOST}:{_PORT}"


def verify_proxy():
    url = get_proxy_url()
    resp = requests.get("https://api.ipify.org/?format=json", proxies={"http": url, "https": url}, timeout=10)
    ip = resp.json().get("ip")
    logger.info("webshare-proxy-ip", ip=ip)
