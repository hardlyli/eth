# ethgui/ws_clients.py

import os
import json
import asyncio
import threading
import websockets
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal
from .config import WS_URL, WS_PROXY
from .logger import logger

# 如需代理，注入 ALL_PROXY
if WS_PROXY:
    os.environ.setdefault("ALL_PROXY", WS_PROXY)
    logger.debug(f"Set ALL_PROXY={WS_PROXY}")

class WSLive(QObject):
    """1m 折线"""
    new_candle = pyqtSignal(dict)  # dict(ts, close)

    def __init__(self, inst: str):
        super().__init__()
        self.inst = inst

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        asyncio.run(self._ws())

    async def _ws(self):
        logger.debug("WSLive connecting…")
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({
                "op":"subscribe",
                "args":[{"channel":"candle1m","instId":self.inst}]
            }))
            logger.debug("WSLive subscribed candle1m")
            async for raw in ws:
                logger.debug(f"WSLive RAW: {raw}")
                d = json.loads(raw)
                if d.get("event"):
                    continue
                arg = d.get("arg", {})
                if arg.get("channel") != "candle1m":
                    continue
                k = d["data"][0]  # [ts,o,h,l,c,vol,…]
                self.new_candle.emit({
                    "ts":    int(k[0]),
                    "close": float(k[4])
                })

class WSSecCandle(QObject):
    """1s K 线聚合（trades）"""
    new_candle = pyqtSignal(dict)  # dict(ts, open, high, low, close, volume)

    def __init__(self, inst: str):
        super().__init__()
        self.inst = inst
        self._bar = None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        asyncio.run(self._ws())

    async def _ws(self):
        logger.debug("WSSecCandle connecting…")
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({
                "op":"subscribe",
                "args":[{"channel":"trades","instId":self.inst}]
            }))
            logger.debug("WSSecCandle subscribed trades")
            async for raw in ws:
                logger.debug(f"WS1S RAW: {raw}")
                d = json.loads(raw)
                if d.get("event"):
                    continue
                arg = d.get("arg", {})
                if arg.get("channel") != "trades":
                    continue
                for t in d.get("data", []):
                    dt = datetime.fromisoformat(t["ts"].replace("Z","+00:00"))
                    ts_ms = int(dt.timestamp()*1000)
                    bucket = (ts_ms//1000)*1000
                    price = float(t["px"])
                    size  = float(t["sz"])
                    bar = self._bar
                    if bar is None or bucket != bar["ts"]:
                        if bar:
                            logger.debug(f"WS1S emit bar: {bar}")
                            self.new_candle.emit(bar.copy())
                        self._bar = {
                            "ts":     bucket,
                            "open":   price,
                            "high":   price,
                            "low":    price,
                            "close":  price,
                            "volume": size
                        }
                    else:
                        bar["high"]   = max(bar["high"], price)
                        bar["low"]    = min(bar["low"], price)
                        bar["close"]  = price
                        bar["volume"] += size

class WSOrderBook(QObject):
    """实时深度 books5"""
    new_book = pyqtSignal(list, list)  # bids, asks

    def __init__(self, inst: str):
        super().__init__()
        self.inst = inst

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        asyncio.run(self._ws())

    async def _ws(self):
        logger.debug("WSOrderBook connecting…")
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({
                "op":"subscribe",
                "args":[{"channel":"books5","instId":self.inst}]
            }))
            logger.debug("WSOrderBook subscribed books5")
            async for raw in ws:
                logger.debug(f"WSOB RAW: {raw}")
                d = json.loads(raw)
                if d.get("event"):
                    continue
                arg = d.get("arg", {})
                if arg.get("channel") != "books5":
                    continue
                ob = d["data"][0]
                bids = ob.get("bids", [])
                asks = ob.get("asks", [])
                logger.debug(f"WSOB data bids={len(bids)} asks={len(asks)}")
                self.new_book.emit(bids, asks)
