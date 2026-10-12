"""Retrying OKX REST client."""
import time
import requests
import certifi
from .config import PROXIES, VERIFY_SSL, OKX_REST_URL
from .logger import logger


class RestClient:
    def __init__(self, timeout=(5.0, 20.0), retries=3):
        self.session = requests.Session()
        self.session.proxies = PROXIES or {}
        self.session.verify = certifi.where() if VERIFY_SSL else False
        if not VERIFY_SSL:
            logger.warning("TLS certificate verification is disabled; HTTPS may be vulnerable to MITM.")
        self.session.headers.update({"User-Agent": "ETH-GUI/RestClient"})
        self.timeout = timeout
        self.retries = max(1, int(retries))

    def close(self):
        self.session.close()

    def get_candles(self, inst: str, bar: str, **params) -> list[list[str]]:
        query = {**params, "instId": inst, "bar": bar}
        last_error = None
        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.get(OKX_REST_URL, params=query, timeout=self.timeout)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("code") != "0":
                    msg = payload.get("msg", "Malformed OKX response") if isinstance(payload, dict) else "Malformed OKX response"
                    raise RuntimeError(f"OKX API error: {msg}")
                rows = payload.get("data")
                if not isinstance(rows, list):
                    raise RuntimeError("OKX response has no candle data list")
                return rows
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                last_error = exc
                logger.warning("REST request failed (attempt %s/%s): %s", attempt, self.retries, exc)
                if attempt < self.retries:
                    time.sleep(min(0.5 * (2 ** (attempt - 1)), 4.0))
        raise last_error
