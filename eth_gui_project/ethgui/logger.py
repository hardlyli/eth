# ethgui/logger.py

import logging
from pathlib import Path
from datetime import datetime
from .config import DEBUG

# 创建日志目录
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# 根据当前时间戳生成每次运行的日志文件名
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = log_dir / f"debug_{timestamp}.log"

# 获取 logger
logger = logging.getLogger("ethgui")
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)

# 控制台输出
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG if DEBUG else logging.INFO)
fmt = "[%(asctime)s] %(levelname)s: %(message)s"
ch.setFormatter(logging.Formatter(fmt, "%H:%M:%S"))
logger.addHandler(ch)

# 文件输出，每次运行一个新文件
fh = logging.FileHandler(log_file, encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S"))
logger.addHandler(fh)

# 简单提示
logger.debug(f"Logging to console and file: {log_file}")
