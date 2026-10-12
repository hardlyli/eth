"""Resilient OKX WebSocket consumers."""
import asyncio
import json
import os
import random
import threading
from datetime import datetime
import websockets
from PyQt6.QtCore import QObject, pyqtSignal
from .config import WS_URL, WS_PROXY
from .logger import logger

if WS_PROXY:
    os.environ.setdefault("ALL_PROXY", WS_PROXY)


class _WSBase(QObject):
    def __init__(self, inst: str):
        super().__init__()
        self.inst = inst
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run(self):
        try:
            asyncio.run(self._reconnect_loop())
        except Exception:
            logger.exception("%s worker stopped unexpectedly", type(self).__name__)

    async def _reconnect_loop(self):
        delay = 1.0
        while not self._stop_event.is_set():
            try:
                await self._ws_session()
                if not self._stop_event.is_set():
                    raise ConnectionError("WebSocket closed by remote peer")
                delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning("%s disconnected: %s; retry in %.1fs", type(self).__name__, exc, delay)
                await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
                delay = min(delay * 2, 30.0)

    async def _ws_session(self):
        raise NotImplementedError

    async def _connect_and_consume(self, channel, on_message):
        async with websockets.connect(
            WS_URL, open_timeout=10, close_timeout=5,
            ping_interval=20, ping_timeout=20, max_size=2**20
        ) as ws:
            await ws.send(json.dumps({
                "op": "subscribe",
                "args": [{"channel": channel, "instId": self.inst}]
            }))
            logger.info("%s subscribed to %s (%s)", type(self).__name__, channel, self.inst)
            async for raw in ws:
                if self._stop_event.is_set():
                    break
                try:
                    message = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("%s received invalid JSON", type(self).__name__)
                    continue
                if message.get("event"):
                    if message.get("event") == "error":
                        raise RuntimeError(f"WebSocket subscription error: {message}")
                    continue
                if message.get("arg", {}).get("channel") != channel:
                    continue
                try:
                    on_message(message)
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    logger.warning("%s ignored malformed %s message: %s", type(self).__name__, channel, exc)


class WSLive(_WSBase):
    """One-minute candle stream."""
    new_candle = pyqtSignal(dict)

    async def _ws_session(self):
        await self._connect_and_consume("candle1m", self._on_message)

    def _on_message(self, message):
        for candle in message.get("data", []):
            self.new_candle.emit({"ts": int(candle[0]), "close": float(candle[4])})


class WSSecCandle(_WSBase):
    """Aggregate trades into one-second OHLCV bars."""
    new_candle = pyqtSignal(dict)

    def __init__(self, inst: str):
        super().__init__(inst)
        self._bar = None
        self._last_trade_id = None

    async def _ws_session(self):
        await self._connect_and_consume("trades", self._on_message)

    def _on_message(self, message):
        trades = sorted(message.get("data", []), key=lambda t: (int(t["ts"]), str(t.get("tradeId", ""))))
        for trade in trades:
            trade_id = trade.get("tradeId")
            if trade_id is not None and trade_id == self._last_trade_id:
                continue
            self._last_trade_id = trade_id
            dt = datetime.fromisoformat(trade["ts"].replace("Z", "+00:00"))
            ts_ms = int(dt.timestamp() * 1000)
            bucket = ts_ms // 1000 * 1000
            price, size = float(trade["px"]), float(trade["sz"])
            if self._bar is None:
                self._bar = self._new_bar(bucket, price, size)
            elif bucket == self._bar["ts"]:
                self._bar["high"] = max(self._bar["high"], price)
                self._bar["low"] = min(self._bar["low"], price)
                self._bar["close"] = price
                self._bar["volume"] += size
            elif bucket > self._bar["ts"]:
                self.new_candle.emit(self._bar.copy())
                self._bar = self._new_bar(bucket, price, size)
            else:
                logger.debug("Ignoring out-of-order trade timestamp=%s current=%s", bucket, self._bar["ts"])

    @staticmethod
    def _new_bar(bucket, price, size):
        return {"ts": bucket, "open": price, "high": price, "low": price, "close": price, "volume": size}


class WSOrderBook(_WSBase):
    """Top-five order book stream."""
    new_book = pyqtSignal(list, list)

    async def _ws_session(self):
        await self._connect_and_consume("books5", self._on_message)

    def _on_message(self, message):
        book = message["data"][0]
        self.new_book.emit(book.get("bids", []), book.get("asks", []))
