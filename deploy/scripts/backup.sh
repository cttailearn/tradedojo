#!/usr/bin/env bash
# =============================================================================
# TradeDojo 数据备份脚本
# - 备份 SQLite 数据库 (含 WAL/SHM)
# - 备份 .env (含密钥,务必加密存储)
# - 备份 logs (近 7 天)
# 用法: crontab 每日 03:00 跑
#   0 3 * * * /opt/tradedojo/deploy/scripts/backup.sh >/var/log/tradedojo-backup.log 2>&1
# =============================================================================
set -euo pipefail

APP_DIR="/opt/tradedojo"
BACKUP_DIR="/var/backups/tradedojo"
KEEP_DAYS=14

mkdir -p "$BACKUP_DIR"

DATE=$(date +%Y%m%d-%H%M%S)
TARGET_DIR="$BACKUP_DIR/$DATE"
mkdir -p "$TARGET_DIR"

echo "[$(date)] start backup -> $TARGET_DIR"

# --- SQLite (WAL 模式下需先 checkpoint 或关连接) ---
if [ -f "$APP_DIR/backend/data/stock.db" ]; then
    # 让数据库合并 WAL 到主库
    sqlite3 "$APP_DIR/backend/data/stock.db" ".backup '$TARGET_DIR/stock.db'" 2>/dev/null \
        || cp -av "$APP_DIR/backend/data/stock.db"* "$TARGET_DIR/"
    echo "  ✓ stock.db"
fi

# --- .env ---
if [ -f "$APP_DIR/.env" ]; then
    cp -a "$APP_DIR/.env" "$TARGET_DIR/env.bak"
    chmod 600 "$TARGET_DIR/env.bak"
    echo "  ✓ .env"
fi

# --- logs (近 7 天) ---
if [ -d "$APP_DIR/backend/logs" ]; then
    tar -czf "$TARGET_DIR/logs.tar.gz" --older-than=0 "$APP_DIR/backend/logs" 2>/dev/null || true
    find "$APP_DIR/backend/logs" -type f -mtime +7 -delete 2>/dev/null || true
    echo "  ✓ logs"
fi

# --- 压缩整个备份 ---
cd "$BACKUP_DIR"
tar -czf "$DATE.tar.gz" "$DATE"
rm -rf "$DATE"

# --- 清理旧备份 ---
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$KEEP_DAYS -delete
echo "[$(date)] done (keep $KEEP_DAYS days)"
