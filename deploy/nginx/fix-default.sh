#!/usr/bin/env bash
# =============================================================================
# 安全修补 default 站点:把 default 完全禁用,tradedojo 接管所有业务。
# 修完还需要用 `certbot --nginx --redirect` 让 certbot 不再追着 default 写。
# =============================================================================
set -euo pipefail

DEFAULT_AVAIL="/etc/nginx/sites-available/default"
DEFAULT_LINK="/etc/nginx/sites-enabled/default"
NGINX_CONF="/etc/nginx/nginx.conf"

echo "→ 备份 default ..."
BAK="/etc/nginx/sites-available/default.bak.$(date +%Y%m%d-%H%M%S)"
cp "$DEFAULT_AVAIL" "$BAK"
echo "  → $BAK"

echo "→ 解除 default 启用(让 tradedojo 全部接管)..."
rm -f "$DEFAULT_LINK"
# 但保留 sites-available 里的 default 文件,以防 certbot 后面续期需要它
# (但 nginx 已经不会加载它,因为没软链)

echo "→ nginx -t ..."
nginx -t

echo ""
echo "→ 后续:certbot 续期若报错 'no site enabled for domain',需手动执行:"
echo "    ln -sf /etc/nginx/sites-available/tradedojo /etc/nginx/sites-enabled/tradedojo"
echo "  然后再次 certbot renew --dry-run"
