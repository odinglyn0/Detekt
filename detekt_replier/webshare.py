from webshare import ApiClient
from secret_manager import get_secret
from log import logger


def get_proxy() -> dict:
    api_key = get_secret("DTKT_WEBSHARE_API_KEY")
    country = get_secret("DTKT_WEBSHARE_COUNTRY")

    client = ApiClient(api_key)
    proxies = client.get_proxy_list(mode="backbone", country_code_in=country)
    results = proxies.get_results()

    if not results:
        logger.error("webshare-no-proxies", country=country)
        raise RuntimeError(f"No Webshare proxies available for {country}")

    p = results[0]
    logger.info("webshare-proxy-loaded", country=p.country_code, host=p.proxy_address)
    return {
        "server": f"http://{p.proxy_address}:{p.port}",
        "username": p.username,
        "password": p.password,
    }
