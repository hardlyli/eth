# ethgui/fetcher.py

from pathlib import Path
import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal
from .rest_client import RestClient
from .config import CACHE_DIR
from .logger import logger

class FetchWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(pd.DataFrame)
    error    = pyqtSignal(str)

    def __init__(self, inst, bar, start_ms, end_ms, cache_path: Path):
        super().__init__()
        self.client    = RestClient()
        self.inst      = inst
        self.bar       = bar
        self.start_ms  = start_ms
        self.end_ms    = end_ms
        self.cache     = cache_path

    def run(self):
        try:
            df = self._load_cache()
            if not df.empty:
                # 如果请求的 start 比缓存最早记录还早，就清空缓存
                earliest_ms = int(df["ts"].iloc[0].timestamp() * 1000)
                if self.start_ms < earliest_ms:
                    logger.debug(f"Requested start {self.start_ms} < cache earliest {earliest_ms}, clearing cache")
                    df = pd.DataFrame(columns=["ts","open","high","low","close","volume","volumeCcy"])

            newest_ms = int(df["ts"].iloc[-1].timestamp() * 1000) if not df.empty else self.start_ms
            if newest_ms < self.end_ms:
                df_new = self._fetch_inc(newest_ms + 1, self.end_ms)
                df = pd.concat([df, df_new]).drop_duplicates("ts").sort_values("ts")
                self._save_cache(df)
            self.finished.emit(df)
        except Exception as e:
            self.error.emit(str(e))

    def _load_cache(self):
        if self.cache.exists():
            logger.debug(f"Loading cache {self.cache}")
            df = pd.read_parquet(self.cache)
            df["ts"] = pd.to_datetime(df["ts"])
            return df.sort_values("ts").reset_index(drop=True)
        return pd.DataFrame(columns=["ts","open","high","low","close","volume","volumeCcy"])

    def _save_cache(self, df: pd.DataFrame):
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(self.cache, index=False)
        logger.debug(f"Saved cache rows={len(df)}")

    def _fetch_inc(self, after_ms, end_ms):
        rows, page, before = [], 0, end_ms
        while True:
            data = self.client.get_candles(self.inst, self.bar, before=before, limit=300)
            if not data:
                break
            rows.extend(data[::-1])
            page += 1
            self.progress.emit(page, -1)
            first_ts = int(data[0][0])
            logger.debug(f"Page {page}: {len(data)} rows, first_ts={first_ts}")
            if len(data) < 300 or first_ts <= after_ms:
                break
            before = first_ts - 1
        self.progress.emit(1, 1)
        if not rows:
            return pd.DataFrame(columns=["ts","open","high","low","close","volume","volumeCcy"])
        trimmed = [r[:7] for r in rows]
        df = pd.DataFrame(trimmed, columns=["ts","open","high","low","close","volume","volumeCcy"])
        df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
        for c in ["open","high","low","close","volume"]:
            df[c] = df[c].astype(float)
        return df
