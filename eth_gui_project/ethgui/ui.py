# ethgui/ui.py

import pandas as pd
import matplotlib.dates as mdates
from pathlib import Path
from datetime import datetime, timedelta, time as dtime

from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QColor, QBrush
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QDateEdit, QComboBox,
    QListWidget, QHBoxLayout, QVBoxLayout, QProgressBar, QStatusBar,
    QTableWidget, QTableWidgetItem, QTabWidget, QDoubleSpinBox,
    QSpinBox, QMessageBox
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import mplfinance as mpf

from .config     import DEFAULT_EPS_MUL, DEFAULT_MIN_HITS, CACHE_DIR
from .fetcher    import FetchWorker
from .indicators import detect_levels
from .ws_clients import WSLive, WSSecCandle, WSOrderBook
from .logger     import logger

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ETH 支撑/阻力 & 实时 K 线")
        self.resize(1280, 760)
        self.inst    = "ETH-USDT"
        self.df_min  = pd.DataFrame()
        self.df_sec  = pd.DataFrame()

        # — Central & Status — #
        central = QWidget(); root = QHBoxLayout(central)
        self.setCentralWidget(central)
        self.status = QStatusBar(); self.setStatusBar(self.status)

        # — Tabs — #
        self.tabs = QTabWidget()
        # 1m 折线
        self.fig1, self.canvas1 = Figure(figsize=(6,4)), None
        self.canvas1 = FigureCanvas(self.fig1)
        t1 = QWidget(); QVBoxLayout(t1).addWidget(self.canvas1)
        self.tabs.addTab(t1, "1m 折线")
        # 1s 蜡烛图
        self.fig2, self.canvas2 = Figure(figsize=(6,4)), None
        self.canvas2 = FigureCanvas(self.fig2)
        t2 = QWidget(); QVBoxLayout(t2).addWidget(self.canvas2)
        self.tabs.addTab(t2, "1s K线")

        # — Controls — #
        today = datetime.utcnow().date()
        self.dte_start = QDateEdit(calendarPopup=True); self.dte_start.setDate(today - timedelta(days=30))
        self.dte_end   = QDateEdit(calendarPopup=True); self.dte_end.setDate(today)
        self.cmb_bar   = QComboBox(); self.cmb_bar.addItems(["1m","5m","15m","1H","4H","1D"])
        self.spin_eps  = QDoubleSpinBox(); self.spin_eps.setRange(0.1,5); self.spin_eps.setValue(DEFAULT_EPS_MUL)
        self.spin_hits = QSpinBox();       self.spin_hits.setRange(1,10); self.spin_hits.setValue(DEFAULT_MIN_HITS)
        self.btn_fetch = QPushButton("抓取/刷新");    self.btn_fetch.clicked.connect(self.fetch)
        self.btn_analy = QPushButton("分析支撑阻力"); self.btn_analy.setEnabled(False); self.btn_analy.clicked.connect(self.analyze)
        self.progress  = QProgressBar(); self.progress.setFixedWidth(140)

        ctl = QHBoxLayout()
        for w in [
            QLabel("开始:"), self.dte_start,
            QLabel("结束:"), self.dte_end,
            QLabel("周期:"), self.cmb_bar,
            QLabel("eps×σ:"), self.spin_eps,
            QLabel("min hits:"), self.spin_hits,
            self.btn_fetch, self.btn_analy, self.progress
        ]:
            ctl.addWidget(w); ctl.setAlignment(w, Qt.AlignmentFlag.AlignVCenter)
        ctl.addStretch()

        # — Right Pane: 支撑/阻力 + 订单簿 — #
        self.list_hits = QListWidget(); self.list_hits.setFixedWidth(200)
        self.table_ob  = QTableWidget(10,3)
        self.table_ob.setHorizontalHeaderLabels(["价","量","买/卖"])
        self.table_ob.setFixedWidth(300)

        right = QVBoxLayout()
        right.addWidget(QLabel("关键价位 (hits)")); right.addWidget(self.list_hits,1)
        right.addWidget(QLabel("实时订单簿 Top5"));  right.addWidget(self.table_ob)
        # — Assemble — #
        left = QVBoxLayout(); left.addWidget(self.tabs,1); left.addLayout(ctl)
        root.addLayout(left,3); root.addLayout(right,1)

        # — WebSocket 实时 — #
        self.ws1m = WSLive(self.inst)
        self.ws1m.new_candle.connect(self.on_live_min)
        self.ws1m.start()

        self.ws1s = WSSecCandle(self.inst)
        self.ws1s.new_candle.connect(self.on_live_sec)
        self.ws1s.start()

        self.wsob = WSOrderBook(self.inst)
        self.wsob.new_book.connect(self.on_orderbook)
        self.wsob.start()

    # — 历史数据抓取 — #
    def fetch(self):
        logger.debug("start_fetch clicked")
        st = self.dte_start.date().toPyDate()
        ed = self.dte_end.date().toPyDate()
        today = datetime.utcnow().date()
        if ed > today:
            QMessageBox.warning(self, "日期错误", f"结束日期 {ed} 在未来，已调整至 {today}")
            ed = today; self.dte_end.setDate(ed)

        s_ms = int(datetime.combine(st, dtime.min).timestamp()*1000)
        e_ms = int(datetime.combine(ed, dtime.max).timestamp()*1000)
        bar  = self.cmb_bar.currentText()
        cache_path = Path(CACHE_DIR)/f"{self.inst}_{bar}.parquet"

        self.worker = FetchWorker(self.inst, bar, s_ms, e_ms, cache_path)
        self.worker.progress.connect(lambda done,_: self.progress.setValue(done))
        self.worker.finished.connect(self.on_fetch_ok)
        self.worker.error.connect(lambda msg: QMessageBox.critical(self, "错误", msg))

        self.progress.setMaximum(0); self.progress.setValue(0)
        self.btn_fetch.setEnabled(False); self.btn_analy.setEnabled(False)
        self.status.showMessage("抓取中…")
        self.worker.start()

    def on_fetch_ok(self, df: pd.DataFrame):
        # 先按用户日期过滤
        st = pd.to_datetime(self.dte_start.date().toPyDate())
        ed = pd.to_datetime(self.dte_end.date().toPyDate()) + pd.Timedelta(days=1) - pd.Timedelta(ms=1)
        df = df[(df["ts"] >= st) & (df["ts"] <= ed)].reset_index(drop=True)

        self.df_min = df
        self.plot_min()
        self.status.showMessage(f"已加载 {len(df)} 根 K 线", 5000)
        self.btn_fetch.setEnabled(True); self.btn_analy.setEnabled(True)
        self.progress.setMaximum(1); self.progress.setValue(1)

    # — 实时 1m 折线 — #
    def on_live_min(self, data: dict):
        if self.df_min.empty: return
        ts = pd.to_datetime(data["ts"], unit="ms")
        if ts <= self.df_min["ts"].iloc[-1]:
            self.df_min.at[self.df_min.index[-1],"close"] = data["close"]
        else:
            new = {"ts":ts,"open":data["close"],"high":data["close"],
                   "low":data["close"],"close":data["close"],
                   "volume":0,"volumeCcy":0}
            self.df_min = pd.concat([self.df_min,pd.DataFrame([new])],ignore_index=True)
        ax = self.fig1.axes[0]
        ax.lines[0].set_data(self.df_min["ts"],self.df_min["close"])
        ax.relim(); ax.autoscale_view()
        self.canvas1.draw_idle()

    # — 实时 1s 蜡烛图 — #
    def on_live_sec(self, bar: dict):
        row = pd.DataFrame([bar]); row["ts"] = pd.to_datetime(row["ts"],unit="ms")
        if self.df_sec.empty or row["ts"].iloc[0] > self.df_sec["ts"].iloc[-1]:
            self.df_sec = pd.concat([self.df_sec,row],ignore_index=True)
        else:
            idx = self.df_sec.index[-1]
            for c in ["open","high","low","close","volume"]:
                self.df_sec.at[idx,c] = bar[c]
        if len(self.df_sec)>300:
            self.df_sec = self.df_sec.iloc[-300:].reset_index(drop=True)
        dfm = self.df_sec.set_index("ts")
        self.fig2.clear()
        mpf.plot(dfm, type="candle", ax=self.fig2.add_subplot(111),
                 axtitle="ETH 1s K线", datetime_format="%H:%M:%S",
                 style="charles", warn_too_much_data=300)
        self.canvas2.draw()

    # — 实时订单簿 Top5 — #
    def on_orderbook(self, bids, asks):
        asks5 = sorted(asks, key=lambda x:float(x[0]))[:5]
        bids5 = sorted(bids, key=lambda x:float(x[0]),reverse=True)[:5]
        rows = asks5 + bids5
        for i in range(10):
            if i < len(rows):
                p,sz = rows[i][0],rows[i][1]
                side = "卖" if i<5 else "买"
                it_p = QTableWidgetItem(f"{float(p):.2f}")
                it_s = QTableWidgetItem(f"{float(sz):.4f}")
                it_d = QTableWidgetItem(side)
                color=QColor(180,0,0) if side=="卖" else QColor(0,180,0)
                for it in (it_p,it_s,it_d): it.setForeground(QBrush(color))
                self.table_ob.setItem(i,0,it_p); self.table_ob.setItem(i,1,it_s); self.table_ob.setItem(i,2,it_d)
            else:
                for c in range(3): self.table_ob.setItem(i,c,QTableWidgetItem(""))

    # — 绘制 1m 折线 — #
    def plot_min(self):
        self.fig1.clear()
        ax = self.fig1.add_subplot(111)
        ax.plot(self.df_min["ts"],self.df_min["close"],linewidth=1)
        ax.set_title("ETH 1m 折线")
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d\n%H:%M'))
        self.fig1.autofmt_xdate()
        self.canvas1.draw()

    # — 支撑/阻力分析 — #
    def analyze(self):
        lv = detect_levels(self.df_min, self.spin_eps.value(), self.spin_hits.value())
        if lv.empty:
            QMessageBox.information(self, "提示", "未检测到支撑/阻力；可调大 eps 或 min hits")
            return
        ax = self.fig1.gca()
        for y in lv["price"]: ax.axhline(y, linestyle="--", alpha=0.7)
        self.canvas1.draw()
        self.list_hits.clear()
        for _,r in lv.iterrows(): self.list_hits.addItem(f"{r.price:.2f}  ({r.hits})")
        self.status.showMessage(f"检测到 {len(lv)} 条支撑/阻力带",5000)
