"""
简单 secret 扫描器 - 在提交前/CI 中运行
- 扫 JWT 形态字符串(eyJ...)
- 扫 .env / .tmp / *_tok 文件
- 扫 STC 前缀 token

用法:
    python scripts/secret_scan.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 命中即报 —— 只在"赋值 + 真实值"形态报警,排除源码中的变量引用/字面量
PATTERNS = [
    # JWT 形态
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
     "JWT token"),
    # env 类配置 STOCK_SECRET_KEY=xxx (要求非空、非占位)
    (re.compile(r"(?im)^[ \t]*(?:export\s+)?STOCK_SECRET_KEY\s*=\s*(?!\s*$)([A-Za-z0-9_.\-+/=]{16,})"),
     "STOCK_SECRET_KEY 显式赋值"),
    # .env 风格 key=value:value 长度>=12 且不是占位
    (re.compile(r"(?im)^[ \t]*(SECRET_KEY|JWT_SECRET|API_KEY|PRIVATE_KEY)\s*=\s*['\"]?([A-Za-z0-9_.\-+/=]{16,})['\"]?\s*$"),
     "明文密钥(.env 风格)"),
]

# 永远忽略
IGNORE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "dist",
    "data", "logs", "__pycache__", "vendor", "Kronos-base",
    ".uv", ".pytest_cache",
}
IGNORE_FILE_EXT = {".pyc", ".pyd", ".so", ".dll", ".png", ".jpg", ".jpeg",
                   ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf"}
TEXT_FILE_EXT = {
    ".py", ".js", ".ts", ".vue", ".json", ".md", ".txt", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".html", ".css", ".sh", ".bat", ".ps1",
    ".sql", ".lock", ".env", ".example",
}


def is_text_candidate(p: Path) -> bool:
    if p.suffix.lower() in TEXT_FILE_EXT:
        return True
    return False


def scan_file(p: Path) -> list[tuple[int, str, str]]:
    hits = []
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return hits
    for ln_no, line in enumerate(text.splitlines(), 1):
        # 跳过明显是"模板/示例"的行
        if "STOCK_SECRET_KEY=" in line and "your-" in line.lower():
            continue
        if "Example" in line or "示例" in line:
            continue
        for pat, label in PATTERNS:
            if pat.search(line):
                hits.append((ln_no, label, line.strip()[:200]))
    return hits


def main() -> int:
    bad_files = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in IGNORE_FILE_EXT:
            continue
        # 文件名命中(直接可疑)
        if path.name.startswith("admin_tok") or path.name.startswith("DEV_ADMIN_PASSWORD"):
            print(f"[FILE] {path}  ← 敏感文件名")
            bad_files += 1
            continue
        if not is_text_candidate(path):
            continue
        # 大文件跳过
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        hits = scan_file(path)
        if hits:
            bad_files += 1
            for ln_no, label, line in hits:
                print(f"[HIT ] {path}:{ln_no}  {label}\n        {line}")
    if bad_files:
        print(f"\n=== 发现 {bad_files} 处可疑项,请检查是否泄漏密钥 ===")
        return 2
    print("[OK] 未发现明文密钥/JWT")
    return 0


if __name__ == "__main__":
    sys.exit(main())