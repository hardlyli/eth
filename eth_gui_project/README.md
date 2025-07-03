# ETH GUI Project

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行

```bash
python -m ethgui.main
```

## 目录结构

- `config.py`：全局配置  
- `logger.py`：统一日志  
- `rest_client.py`：OKX REST 封装  
- `ws_clients.py`：各类 WebSocket 客户端  
- `fetcher.py`：历史数据抓取线程（Parquet 缓存）  
- `indicators.py`：支撑/阻力算法  
- `ui.py`：PyQt6 窗口布局与信号  
- `main.py`：入口
