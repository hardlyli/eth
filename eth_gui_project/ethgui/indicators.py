"""Technical indicators and volatility-aware support/resistance zones."""
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN


def detect_levels(df: pd.DataFrame, eps_mul: float, min_hits: int) -> pd.DataFrame:
    """Cluster swing highs/lows into price zones; eps_mul scales ATR."""
    columns = ["price", "hits"]
    required = {"high", "low", "close"}
    if df is None or df.empty or not required.issubset(df.columns):
        return pd.DataFrame(columns=columns)
    if min_hits < 1 or eps_mul <= 0:
        raise ValueError("eps_mul and min_hits must be positive")

    data = df.loc[:, ["high", "low", "close"]].copy()
    for col in data.columns:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
    if len(data) < 5:
        return pd.DataFrame(columns=columns)

    highs, lows = data["high"].to_numpy(float), data["low"].to_numpy(float)
    closes = data["close"].to_numpy(float)
    pivots = []
    for i in range(2, len(data) - 2):
        wh, wl = highs[i - 2:i + 3], lows[i - 2:i + 3]
        if highs[i] >= wh.max() and highs[i] > wh[:2].max() and highs[i] > wh[3:].max():
            pivots.append(highs[i])
        if lows[i] <= wl.min() and lows[i] < wl[:2].min() and lows[i] < wl[3:].min():
            pivots.append(lows[i])
    if len(pivots) < min_hits:
        return pd.DataFrame(columns=columns)

    prev_close = np.r_[closes[0], closes[:-1]]
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_close), np.abs(lows - prev_close)))
    atr = float(pd.Series(tr).rolling(14, min_periods=1).mean().iloc[-1])
    if not np.isfinite(atr) or atr <= 0:
        atr = max(float(np.nanmedian(np.abs(closes)) * 0.001), np.finfo(float).eps)
    eps = max(atr * float(eps_mul), np.finfo(float).eps)
    labels = DBSCAN(eps=eps, min_samples=int(min_hits)).fit_predict(np.asarray(pivots).reshape(-1, 1))
    points = pd.DataFrame({"price": pivots, "cluster": labels})
    levels = (
        points[points["cluster"] != -1]
        .groupby("cluster", as_index=False)
        .agg(price=("price", "median"), hits=("price", "size"))
        .sort_values("price")
        .reset_index(drop=True)
    )
    return levels[columns].reset_index(drop=True)
