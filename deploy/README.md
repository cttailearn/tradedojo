# TradeDojo 服务器部署

域:`cttai.art` / `www.cttai.art` / `api.cttai.art`(certbot 已签 api 子域)

## 部署后的访问拓扑

```
┌─────────────────────────────────────────────────────────────────┐
│                            终端用户                              │
│   ┌──────────────┐    ┌──────────────┐    ┌─────────────┐      │
│   │  浏览器 SPA  │    │   手机 H5    │    │  原生 APK   │      │
│   └──────┬───────┘    └──────┬───────┘    └──────┬──────┘      │
└──────────┼──────────────────┼───────────────────┼─────────────┘
           │ cttai.art         │                   │ api.cttai.art
           │ (含 www)          │                   │
           ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Nginx (systemd)                            │
│  cttai.art:443         → SPA 静态 + SPA fallback                │
│  api.cttai.art:443     → 反代 127.0.0.1:8000                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ http://127.0.0.1:8000
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│          FastAPI (systemd: tradedojo.service)                   │
│   /api/* 业务  +  /train/* 训练  +  SPA 兜底(index.html)        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                        SQLite + WAL 或 PostgreSQL
                      data/stock.db / STOCK_DB_DRIVER=postgres
```

## 文件清单

```
deploy/
├── README.md                  ← 本文件
├── env/.env.production        ← 生产 .env 模板
├── nginx/tradedojo.conf       ← Nginx(双 server: SPA + API)
├── systemd/tradedojo.service  ← systemd unit
└── scripts/
    ├── deploy.sh              ← 一键部署
    ├── cert-issue.sh          ← 申请证书(webroot,不破坏 nginx)
    └── backup.sh              ← 数据备份
```

## 一次性部署流程

### 1. 上传项目到服务器

```bash
# 本地
scp -r d:/AI/tradedojo root@cttai.art:/opt/

# 或
ssh root@cttai.art
git clone https://github.com/your-org/tradedojo.git /opt/tradedojo
```

### 2. 准备 .env

```bash
ssh root@cttai.art
cp /opt/tradedojo/deploy/env/.env.production /opt/tradedojo/.env
nano /opt/tradedojo/.env
# 改 3 项:
#   STOCK_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
#   STOCK_ADMIN_PASSWORD=<强密码>
#   STOCK_CORS_ORIGINS 已经填好(https://cttai.art,https://www.cttai.art,https://api.cttai.art,http://localhost:5173)
chmod 600 /opt/tradedojo/.env
```

### 3. 申请证书

```bash
# api.cttai.art 已签,这里只补签 cttai.art + www.cttai.art
bash deploy/scripts/cert-issue.sh you@example.com
```

### 4. 部署

```bash
chmod +x deploy/scripts/*.sh
bash deploy/scripts/deploy.sh
```

### 5. 启用每日备份

```bash
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/tradedojo/deploy/scripts/backup.sh >/var/log/tradedojo-backup.log 2>&1") | crontab -
```

## 日常管理

```bash
# 后端
systemctl status tradedojo
systemctl restart tradedojo
journalctl -u tradedojo -f

# Nginx
nginx -t
systemctl reload nginx
journalctl -u nginx -f

# 健康检查
curl -sS https://api.cttai.art/api/health
curl -sS -o /dev/null -w "%{http_code}\n" https://cttai.art

# certbot
certbot certificates        # 列出全部证书
systemctl list-timers | grep certbot   # 查自动续期 cron
```

## 与 certbot 的协作(关键)

| 项目 | 状态 |
|------|------|
| `certbot --nginx` 第一次跑 → 改写 `/etc/nginx/sites-enabled/default` | ✅ 已发生 |
| `tradedojo.conf` 引用 `/etc/letsencrypt/live/<domain>/*.pem` 路径(避开 `default` 站点) | ✅ 我们的配置文件 |
| `certbot renew` 自动续期(每 60 天检查)→ 改 `/etc/letsencrypt/live/<domain>/`,不影响 nginx 因为它只动文件不动 server_name | ✅ 不冲突 |
| `certbot --nginx` **再次手动跑** → 改 `default` 站点,但我们的 `tradedojo.conf` 是独立站点,**完全不受影响** | ✅ 安全 |

**重要约定**:
- 不要让 `certbot --nginx` 选中 `tradedojo.conf` (它会自动改写我们的 80/443 块)
- 真要补签证书,**只用 `certbot certonly --webroot`**,不用 `--nginx`
- `deploy/scripts/cert-issue.sh` 已经统一用 webroot 方式,符合约定

## 域名 → 客户端约定

| 客户端 | Base URL | 鉴权方式 |
|--------|----------|----------|
| SPA (Web) | `https://cttai.art` 或 `https://www.cttai.art` | httpOnly cookie + Bearer |
| 手机 H5 | `https://cttai.art` | 同上 |
| Android APK | `https://api.cttai.art` | **Bearer token**(`/api/train/login`) |
| iOS (Future) | `https://api.cttai.art` | Bearer token |

## 维护 checklist

- [ ] 每日 03:00 自动备份(check crontab)
- [ ] 每月检查 `certbot certificates`(看到期时间)
- [ ] 每 90 天轮换 `STOCK_SECRET_KEY`(全员重新登录)
- [ ] 升级:`cd /opt/tradedojo && git pull && systemctl restart tradedojo && cd frontend && npm run build`
- [ ] 数据库膨胀时清理:`DELETE FROM update_log WHERE created_at < datetime('now','-30 day'); VACUUM;`

## 登录防爆破(2026-08-03 起)

管理端与训练端登录均启用账号锁定:**连续 5 次失败锁定 15 分钟**(返回 HTTP 429),锁定期间即使密码正确也拒绝。同时保留 IP 维度限速(`LOGIN_RATE_LIMIT=10/minute`)。

- 训练端 `training_user` 新增列:`failed_attempts INTEGER DEFAULT 0`、`last_failed_login TEXT`。
- **老库(SQLite/PG 均已部署的库)无需手动 ALTER**:后端启动/首次登录时 `_ensure_login_lock_columns()` 自动探测并补列(SQLite 用 `PRAGMA table_info`,PG 用 `information_schema.columns`),新装环境由 `schema.sql` / `schema_pg.sql` 直接建好。
- 服务器升级只需 `git pull && systemctl restart tradedojo`,无需任何数据库手工操作。
- 时区约定:失败时间戳由应用层(Python 本地时区)写入,与锁定窗口判断同基准,不依赖数据库 `localtime`。
