# Security Policy

## 已实施的安全措施(P0 + P1)

### 认证与授权
- JWT 签名密钥强制要求(无默认值,生产未设置即拒绝启动)
- 默认管理员密码强制要求(生产未设置即拒绝启动;dev 模式生成强随机密码写入 `logs/DEV_ADMIN_PASSWORD.txt`)
- access token 绑定客户端 UA 指纹(IP/UA 变化即 token 失效)
- refresh token(7 天) + 旋转策略,支持吊销(单条/全部)
- 登录限速(`10/minute`)+ 失败计数(5 次锁定 15 分钟)
- 注册限速(`5/minute`)
- 全局限速(`300/minute`)
- 统一登录错误文案,防账号枚举

### Cookie / CSRF
- access / refresh: `httpOnly + Secure(prod) + SameSite=Lax`
- CSRF 双 cookie 模式: 写操作校验 `X-CSRF-Token` header
- 前端 `withCredentials=true`,自动读写 CSRF

### 响应头 / 安全策略
- `Strict-Transport-Security`(生产)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy`(基础)
- `Permissions-Policy` 最小化浏览器能力

### 数据 / 日志
- 密码 PBKDF2-HMAC-SHA256 (200k 轮)
- 全局异常处理脱敏(对外仅暴露 `error_id`)
- 日志敏感字段过滤(Authorization/password/token)
- 日志 `RotatingFileHandler` (20MB × 10)

### 配置 / 部署
- `.env` / `*.tmp` / `admin_tok*` / `*_tok*` / `DEV_ADMIN_PASSWORD*` 已加入 `.gitignore`
- `scripts/secret_scan.py` 在提交前/CI 中扫描明文密钥
- `scripts/backup_sqlite.py` 一致性备份(SQLite `.backup()`)

---

## 上线 Checklist

- [ ] 设置 `STOCK_SECRET_KEY` (≥32 字符强随机)
- [ ] 设置 `STOCK_ADMIN_PASSWORD` (首次创建管理员时必须)
- [ ] 设置 `STOCK_CORS_ORIGINS` (具体域名,禁用 `*`)
- [ ] 反向代理(Nginx/Caddy)强制 HTTPS + 设置 HSTS
- [ ] 数据库迁移到 PostgreSQL(目前 SQLite 仅适合单实例)
- [ ] 任务队列迁移到 Celery/Arq(目前内存 threading)
- [ ] 接入 Sentry / 集中式日志
- [ ] CI 加入 `scripts/secret_scan.py` + `ruff` + `eslint` + 测试
- [ ] 定期执行 `scripts/backup_sqlite.py`(或 pg_dump)并异地存储
- [ ] 监控 / 告警(`/api/health` + DB 写入失败 + 限速命中告警)

---

## 已知限制 / 待办(P2)

- JWT 仍是 HS256 + 单密钥,多实例下建议升级 RS256 + JWKS
- 训练端 (`/api/train/*`) 仍走 Bearer header(因为跨域 cookie 场景更复杂),待统一
- `train_token` 表对老代码兼容保留,新流程推荐只用 JWT + refresh
- 后台任务状态在内存,重启即丢失,需要持久化
- 调度器在主进程 `threading` 中跑,多 worker / 容器重启会失效

---

## 报告漏洞

如发现安全问题,请联系项目维护者(不要直接提交 issue),并附上复现步骤与影响评估。