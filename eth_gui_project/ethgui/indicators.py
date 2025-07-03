import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

def detect_levels(df: pd.DataFrame, eps_mul: float, min_hits: int) -> pd.DataFrame:
    pivots = []
    for i in range(2, len(df)-2):
        if (
            df["high"][i] == max(df["high"][i-2:i+3])
            or df["low"][i] == min(df["low"][i-2:i+3])
        ):
            pivots.append(df["close"][i])
    if len(pivots) < min_hits:
        return pd.DataFrame(columns=["price","hits"])
    X = np.array(pivots).reshape(-1,1)
    kms = DBSCAN(eps=df["close"].std()*eps_mul, min_samples=min_hits).fit(X)
    pv = pd.DataFrame({"price":pivots, "cluster":kms.labels_})
    lv = (
        pv.query("cluster!=-1")
          .groupby("cluster")
          .agg(price=("price","mean"), hits=("price","size"))
          .reset_index(drop=True)
          .sort_values("price")
    )
    return lv
