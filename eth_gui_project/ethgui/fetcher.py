"""Historical candle loading and local Parquet cache."""
from pathlib import Path
import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal
from .rest_client import RestClient
from .logger import logger

COLUMNS = ["ts", "open", "high", "low", "close", "volume", "volumeCcy"]


class FetchWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(pd.DataFrame)
    error = pyqtSignal(str)

    def __init__(self, inst, bar, start_ms, end_ms, cache_path: Path):
        super().__init__()
        self.client = RestClient()
        self.inst, self.bar = inst, bar
        self.start_ms, self.end_ms = int(start_ms), int(end_ms)
        self.cache = Path(cache_path)

    def run(self):
        try:
            if self.start_ms > self.end_ms:
                raise ValueError("start_ms must be <= end_ms")
            cached = self._load_cache()
            # Always fetch the requested interval: cached data may have internal gaps.
            downloaded = self._fetch_range(self.start_ms, self.end_ms)
            frames = [x for x in (cached, downloaded) if not x.empty]
            result = pd.concat(frames, ignore_index=True) if frames else self._empty()
            result = self._normalise(result)
            self._save_cache(result)
            start, end = pd.to_datetime(self.start_ms, unit="ms"), pd.to_datetime(self.end_ms, unit="ms")
            result = result[(result.ts >= start) & (result.ts <= end)].reset_index(drop=True)
            self.finished.emit(result)
        except Exception as exc:
            logger.exception("Historical candle fetch failed")
            self.error.emit(str(exc))
        finally:
            self.client.close()

    @staticmethod
    def _empty():
        return pd.DataFrame(columns=COLUMNS)

    @staticmethod
    def _normalise(df):
        if df.empty:
            return FetchWorker._empty()
        df = df.copy()
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)
        for col in ["open", "high", "low", "close", "volume", "volumeCcy"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["ts", "open", "high", "low", "close"])
        return df[COLUMNS].drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)

    def _load_cache(self):
        if not self.cache.exists():
            return self._empty()
        try:
            df = pd.read_parquet(self.cache)
            if not set(COLUMNS).issubset(df.columns):
                logger.warning("Ignoring cache with unexpected columns: %s", self.cache)
                return self._empty()
            return self._normalise(df[COLUMNS])
        except Exception:
            logger.exception("Could not read cache %s; rebuilding", self.cache)
            return self._empty()

    def _save_cache(self, df):
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(self.cache, index=False)
        logger.debug("Saved cache rows=%s path=%s", len(df), self.cache)

    def _fetch_range(self, start_ms: int, end_ms: int):
        """Page backwards through OKX candles; stop if the cursor fails to advance."""
        collected, cursor, page, seen = [], end_ms, 0, set()
        while cursor >= start_ms:
            if cursor in seen:
                logger.warning("Repeated candle pagination cursor %s; stopping", cursor)
                break
            seen.add(cursor)
            rows = self.client.get_candles(self.inst, self.bar, before=cursor, limit=300)
            if not rows:
                break
            timestamps = []
            for row in rows:
                try:
                    ts = int(row[0])
                    timestamps.append(ts)
                    if start_ms <= ts <= end_ms:
                        collected.append(row[:len(COLUMNS)])
                except (IndexError, TypeError, ValueError):
                    continue
            page += 1
            self.progress.emit(page, -1)
            if not timestamps:
                logger.warning("Candle page had no valid timestamps; stopping")
                break
            oldest = min(timestamps)
            if oldest <= start_ms or len(rows) < 300:
                break
            next_cursor = oldest - 1
            if next_cursor >= cursor:
                logger.warning("Candle cursor did not advance (%s -> %s)", cursor, next_cursor)
                break
            cursor = next_cursor
        self.progress.emit(1, 1)
        if not collected:
            return self._empty()
        return self._normalise(pd.DataFrame(collected, columns=COLUMNS))
