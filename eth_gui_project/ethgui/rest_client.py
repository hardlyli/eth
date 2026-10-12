import requests, certifi
from .config import PROXIES, VERIFY_SSL, OKX_REST_URL
from .logger import logger

class RestClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.proxies = PROXIES or None
        self.session.verify  = certifi.where() if VERIFY_SSL is True else VERIFY_SSL
        self.session.headers.update({"User-Agent": "ETH-GUI/RestClient"})

    def get_candles(self, inst: str, bar: str, **params) -> list[list[str]]:
        url = OKX_REST_URL
        params.update(instId=inst, bar=bar)
        for attempt in range(1, 4):
            try:
                logger.debug(f"REST GET {url} params={params}")
                r = self.session.get(url, params=params, timeout=20)
                r.raise_for_status()
                data = r.json()
                if data.get("code") != "0":
                    raise RuntimeError(data.get("msg", "OKX error"))
                return data["data"]
            except Exception as e:
                logger.warning(f"REST error {e} (retry {attempt}/3)")
                if attempt == 3:
                    raise
        return []
