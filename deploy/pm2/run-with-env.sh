#!/usr/bin/env bash
# =============================================================================
# pm2 启动包装:从 /opt/tradedojo/.env 注入环境变量,再启 pm2
# 用法(必须 sudo,因为 .env 可能 600 权限):
#   sudo bash deploy/pm2/run-with-env.sh start   # 启动
#   sudo bash deploy/pm2/run-with-env.sh stop    # 停止
#   sudo bash deploy/pm2/run-with-env.sh restart # 重启
#   sudo bash deploy/pm2/run-with-env.sh status  # 状态
#   sudo bash deploy/pm2/run-with-env.sh logs    # 看日志
# =============================================================================
set -euo pipefail

APP_DIR="/opt/tradedojo"
CONF="$APP_DIR/deploy/pm2/ecosystem.config.js"
LOG_DIR="$APP_DIR/backend/logs"

# ---- 加载 .env 到当前 shell ----
if [ ! -f "$APP_DIR/.env" ]; then
    echo "✗ 找不到 $APP_DIR/.env"
    exit 1
fi
set -a
# shellcheck disable=SC1091
. "$APP_DIR/.env"
set +a

# ---- 确保 logs 目录存在且可写 ----
mkdir -p "$LOG_DIR"
chmod 755 "$LOG_DIR"

# ---- 装 pm2-linux-startup(一次性) ----
if ! pm2 list 2>/dev/null | grep -q 'pm2'; then
    echo "[1/3] 首次启动,初始化 pm2 开机自启 ..."
    pm2 install pm2-logrotate
fi

# ---- 子命令 ----
ACTION="${1:-start}"

case "$ACTION" in
    start)
        # 写入 .env 内容到 pm2 save 之后会持续生效,
        # 但 env.* 只在 start 时读一次,所以这里把变量集中导出
        echo "[2/3] 启动应用 ..."
        cd "$APP_DIR"
        # 用 ecosystem 时,env.* 默认从上面 set -a 注入到 pm2 进程
        # 但 pm2 不会捕获到 shell 临时变量;这里走 --update-env
        pm2 start "$CONF" --update-env
        ;;
    stop)
        pm2 stop tradedojo
        ;;
    restart)
        pm2 restart tradedojo --update-env
        ;;
    reload)
        pm2 reload tradedojo
        ;;
    status)
        pm2 list
        ;;
    logs)
        pm2 logs tradedojo --lines 200
        ;;
    monit)
        pm2 monit
        ;;
    delete)
        pm2 delete tradedojo
        ;;
    save)
        pm2 save
        ;;
    startup)
        # 返回 systemd 命令,需 sudo 执行
        pm2 startup
        ;;
    *)
        echo "用法: $0 {start|stop|restart|reload|status|logs|monit|delete|save}"
        exit 1
        ;;
esac
