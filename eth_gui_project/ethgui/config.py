from pathlib import Path

# ---- 调试开关 ----
DEBUG = True

# ---- 缓存 & 代理 ----
CACHE_DIR = Path("cache")
PROXIES = {
    # "https": "http://127.0.0.1:7890",
    # "http":  "http://127.0.0.1:7890",
}
VERIFY_SSL = False  # True 或 证书文件路径

# ---- 字体 & 算法参数 ----
FONT_NAME      = "Microsoft YaHei"
DEFAULT_EPS_MUL  = 1.2
DEFAULT_MIN_HITS = 2

# ---- OKX 接口地址 ----
OKX_REST_URL = "https://www.okx.com/api/v5/market/candles"
# WebSocket 市场行情地址根据官方文档应使用 /ws/v5/market
WS_URL       = "wss://ws.okx.com:8443/ws/v5/market"
WS_PROXY = "http://127.0.0.1:7890"
