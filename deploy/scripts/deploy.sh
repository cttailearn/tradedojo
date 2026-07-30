#!/usr/bin/env bash
# =============================================================================
# TradeDojo 一键部署 (systemd 或 pm2 两选一)
# 默认 systemd(已签 api.cttai.art 证书,不动 default 站点)
# 用法:
#   bash deploy/scripts/deploy.sh            # 默认 systemd
#   PM2=1 bash deploy/scripts/deploy.sh     # 走 pm2
# =============================================================================
set -euo pipefail

USE_PM2="${PM2:-0}"
APP_DIR="/opt/tradedojo"
BACKEND_DIR="$APP_DIR/backend"
NGINX_CONF_SRC="$APP_DIR/deploy/nginx/tradedojo.conf"

echo "================================================================="
echo "  TradeDojo 一键部署"
echo "  APP_DIR = $APP_DIR"
echo "  管理器  = ${USE_PM2} (1=pm2, 0=systemd)"
echo "================================================================="

# --- 前置:系统包 ---
echo "[1/8] 安装系统依赖 ..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv curl git nginx sqlite3 >/dev/null

# uv
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # shellcheck disable=SC1091
    export PATH="$HOME/.local/bin:$PATH"
fi

# node / pm2 (仅当 PM2=1)
if [ "$USE_PM2" = "1" ]; then
    if ! command -v node >/dev/null 2>&1; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null
        apt install -y -qq nodejs >/dev/null
    fi
    if ! command -v pm2 >/dev/null 2>&1; then
        npm install -g pm2 pm2-logrotate >/dev/null
    fi
fi

# --- 项目目录 ---
echo "[2/8] 确保项目位于 $APP_DIR ..."
if [ ! -d "$APP_DIR" ]; then
    echo "  ✗ 项目目录不存在,请先 git clone 到 $APP_DIR"
    exit 1
fi

# --- .env ---
echo "[3/8] 检查 .env ..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/deploy/env/.env.production" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo "  → 已复制 .env 模板到 $APP_DIR/.env,请编辑后再次运行本脚本"
fi

# --- 后端依赖 ---
echo "[4/8] uv sync ..."
cd "$BACKEND_DIR"
uv sync --quiet

# --- 前端构建 ---
echo "[5/8] 前端构建 ..."
cd "$APP_DIR/frontend"
if [ ! -d node_modules ]; then
    npm ci --silent
fi
npm run build --silent

# --- 进程管理器 ---
echo "[6/8] 安装 进程管理器 ..."
if [ "$USE_PM2" = "1" ]; then
    # 把包装脚本设为可执行
    chmod +x "$APP_DIR/deploy/pm2/run-with-env.sh"
    # 启动
    bash "$APP_DIR/deploy/pm2/run-with-env.sh" start
    # 保存快照(开机自启用)
    pm2 save
    echo "  → pm2 已启动"
    echo "  → 下一步: pm2 startup  (按提示 sudo 一次,然后 pm2 save)"
else
    # systemd
    cp "$APP_DIR/deploy/systemd/tradedojo.service" /etc/systemd/system/tradedojo.service
    systemctl daemon-reload
    systemctl enable tradedojo
    echo "  → systemd unit 已安装"
fi

# --- nginx ---
echo "[7/8] 安装 nginx 配置 ..."
# 关键:用数字前缀让 nginx 先加载我们的配置
# nginx.conf 中 sites-enabled/* 按字母序加载,default < tradedojo 会导致 default 抢占我们的 vhost
# 名字改为 0tradedojo 后字母序第一,trade 每个 server_name 精确命中都走我们的块,default 永远不命中

SITE_NAME="0tradedojo"

# 清掉两种可能的旧名
rm -f /etc/nginx/sites-enabled/tradedojo
rm -f /etc/nginx/sites-enabled/0tradedojo

# 把目标文件拷成实文件(不是软链),避免源也是 symlink 时递归
rm -f /etc/nginx/sites-available/$SITE_NAME
cp "$NGINX_CONF_SRC" /etc/nginx/sites-available/$SITE_NAME
chmod 644 /etc/nginx/sites-available/$SITE_NAME

ln -s /etc/nginx/sites-available/$SITE_NAME /etc/nginx/sites-enabled/$SITE_NAME

# 让 nginx(www-data)能读到前端 chunk
if [ -d "$APP_DIR/frontend/dist" ]; then
    chmod o+x /root 2>/dev/null || true
    chmod -R o+rX "$APP_DIR/frontend/dist" 2>/dev/null || true
fi

nginx -t
systemctl reload nginx

# --- 启动 ---
echo "[8/8] 重启服务 ..."
if [ "$USE_PM2" = "1" ]; then
    bash "$APP_DIR/deploy/pm2/run-with-env.sh" restart
    sleep 2
    if pm2 list | grep -q 'tradedojo.*online'; then
        echo "  ✓ pm2: tradedojo is online"
    else
        echo "  ✗ pm2: tradedojo 启动失败"
        pm2 logs tradedojo --lines 50
        exit 1
    fi
else
    systemctl restart tradedojo
    sleep 2
    if systemctl is-active --quiet tradedojo; then
        echo "  ✓ systemd: tradedojo is active"
    else
        echo "  ✗ tradedojo 启动失败,查看日志:"
        journalctl -u tradedojo -n 50
        exit 1
    fi
fi

echo ""
echo "================================================================="
echo "  部署完成 ✓  (管理器: $( [ "$USE_PM2" = "1" ] && echo pm2 || echo systemd ))"
echo "  测试访问:"
echo "    https://cttai.art              (前端)"
echo "    https://api.cttai.art/api/health"
echo ""
if [ "$USE_PM2" = "1" ]; then
    echo "  管理命令:"
    echo "    bash deploy/pm2/run-with-env.sh status"
    echo "    bash deploy/pm2/run-with-env.sh logs"
    echo "    bash deploy/pm2/run-with-env.sh monit"
    echo "    pm2 save  ; sudo pm2 startup"
else
    echo "  管理命令:"
    echo "    systemctl {status|restart} tradedojo"
    echo "    journalctl -u tradedojo -f"
fi
echo "================================================================="
