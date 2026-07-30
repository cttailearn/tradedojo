#!/usr/bin/env bash
# =============================================================================
# 申请 Let's Encrypt 证书 (默认: cttai.art + www.cttai.art)
# 前置:
#   - 域名已解析到本机公网 IP
#   - /etc/nginx 已装好
#   - 如已签过 api.cttai.art,本脚本只补签 cttai.art + www.cttai.art
# 用法:
#   sudo bash deploy/scripts/cert-issue.sh you@example.com
#   (邮箱可省,默认 Webmaster@<域>)
# =============================================================================
set -euo pipefail

# ---- 参数 ----
DOMAIN="cttai.art"
WILD_DOMAIN="www.${DOMAIN}"
API_DOMAIN="api.${DOMAIN}"
EMAIL="${1:-webmaster@${DOMAIN}}"

echo "================================================================="
echo "  申请证书"
echo "  主页:    $DOMAIN + $WILD_DOMAIN"
echo "  API:    $API_DOMAIN (若未签会一起签)"
echo "  邮箱:   $EMAIL"
echo "================================================================="

# ---- 安装 certbot ----
echo "[1/5] 安装 certbot ..."
apt-get install -y -qq certbot python3-certbot-nginx >/dev/null

# ---- 检测已有证书(不重复签) ----
echo "[2/5] 检查已有证书 ..."
declare -a NEED
for d in "$DOMAIN" "$WILD_DOMAIN"; do
    if [ ! -f "/etc/letsencrypt/live/${d}/fullchain.pem" ]; then
        NEED+=("$d")
    else
        echo "  ✓ ${d} 已存在"
    fi
done
[ ! -f "/etc/letsencrypt/live/${API_DOMAIN}/fullchain.pem" ] && NEED+=("$API_DOMAIN")

# ---- 用 webroot 申请(不影响现有 nginx) ----
# 让 webroot 临时指向 /var/www/html(已经在 nginx 里预留了 /.well-known/acme-challenge/)
echo "[3/5] 准备 webroot ..."
mkdir -p /var/www/html
chmod 755 /var/www/html

if [ ${#NEED[@]} -eq 0 ]; then
    echo "  ✓ 所有证书已存在,跳过申请"
else
    echo "[4/5] 申请证书: ${NEED[*]} ..."
    # shellcheck disable=SC2068
    certbot certonly --webroot -w /var/www/html \
        --non-interactive --agree-tos \
        -m "$EMAIL" \
        $(printf -- '-d %s ' "${NEED[@]}")

    # 这里只签不部署;部署由 deploy.sh 接管(写入 tradedojo.conf 的 ssl_certificate 行)
fi

# ---- 续期测试 ----
echo "[5/5] 续期测试 ..."
certbot renew --dry-run

# ---- 提示 ----
echo ""
echo "  ✓ 证书路径:"
for d in "$DOMAIN" "$WILD_DOMAIN" "$API_DOMAIN"; do
    if [ -f "/etc/letsencrypt/live/${d}/fullchain.pem" ]; then
        echo "    /etc/letsencrypt/live/${d}/fullchain.pem"
    fi
done
echo ""
echo "  下一步: bash deploy/scripts/deploy.sh"
