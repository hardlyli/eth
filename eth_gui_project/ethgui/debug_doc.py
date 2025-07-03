# ethgui/debug_doc.py
import os
import sys, platform, json
from pathlib import Path
from datetime import datetime
from .config import DEBUG, CACHE_DIR, PROXIES, VERIFY_SSL, FONT_NAME, DEFAULT_EPS_MUL, DEFAULT_MIN_HITS

def generate_debug_doc():
    """生成 debug_report.md，包含环境信息和当前配置"""
    now = datetime.now().isoformat(timespec="seconds")
    lines = [
        f"# Debug Report  —  {now}",
        "",
        "## 环境",
        f"- Python: {sys.version.replace(os.linesep, ' ')}",
        f"- Platform: {platform.platform()}",
        "",
        "## 配置",
        "```json",
        json.dumps({
            "DEBUG": DEBUG,
            "CACHE_DIR": str(CACHE_DIR),
            "PROXIES": PROXIES,
            "VERIFY_SSL": VERIFY_SSL,
            "FONT_NAME": FONT_NAME,
            "DEFAULT_EPS_MUL": DEFAULT_EPS_MUL,
            "DEFAULT_MIN_HITS": DEFAULT_MIN_HITS
        }, indent=2, ensure_ascii=False),
        "```",
        "",
        "## 说明",
        "- `logs/debug.log` 包含详细运行日志。",
        "- 本文件可用于排查启动/运行过程中的配置与环境问题。"
    ]
    out = Path("debug_report.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[DEBUG] Generated debug report at {out}", flush=True)
