# TradeDojo 项目功能测试报告

- **报告时间**: `2026-07-29 09:12 - 09:16 (UTC+8)`
- **后端地址**: `http://127.0.0.1:8000`
- **运行模式**: `STOCK_DEV=1`(开发模式)
- **测试账号**: 管理员 `ctt / ctt584520`(数据库预存在); 训练用户 `smokefull_<ts>` 运行时自动注册
- **测试脚本**:
  - `d:\AI\tradedojo\scripts\test_full_api.py` — 全量端到端 API + 前端路由
  - `d:\AI\tradedojo\backend\tests\test_system.py` — 不依赖网络的单元测试
  - `d:\AI\tradedojo\scripts\test_api.py` — 既有冒烟测试脚本

---

## 1. 总览

| 类型 | 通过 | 失败 | 总数 | 通过率 |
|------|-----:|-----:|-----:|-------:|
| **后端单元测试** (`tests/test_system.py`) | 8 | 0 | 8 | 100% |
| **端到端 API 测试** (`scripts/test_full_api.py`) | 41 | 0 | 41 | 100% |
| **既有冒烟测试** (`scripts/test_api.py`) | 13 | 1 | 14 | 92.9% |
| **合计** | **62** | **1** | **63** | **98.4%** |

> 注:`scripts/test_api.py` 中 1 个 `[FAIL]` 是测试脚本自身校验字段(`access_token`)误判 — 后端登录响应是 `data: {access_token, ...}` 包装格式,脚本体直接读根字段;实测登录本身返回 200 且 `data.access_token` 存在,功能正常。

---

## 2. 后端单元测试 (8/8 PASS)

| # | 用例 | 说明 |
|--:|------|------|
| 1 | 数据库初始化 | `init_db` 创建 `stock_list / kline_daily / kline_minute / index_daily / update_log` 等表 |
| 2 | 断点续传 | `CheckpointManager` 完成/失败标记 + 重启恢复 |
| 3 | 重试耗尽保护 | 超过 `max_retry=2` 后不再 retry |
| 4 | WAL 模式 | `journal_mode = wal`,并发读写友好 |
| 5 | 写入/替换 | `INSERT OR REPLACE` 行为正确 |
| 6 | 市场代码识别 | `600000→sh` / `000001→sz` / `300750→sz` / `688981→sh` / `833454→bj` |
| 7 | Backtrader 集成 | `SmaCrossStrategy` / `MomentumStrategy` / `BuyHoldStrategy` 均导入成功 |
| 8 | A 股手续费 | 买入 0.03% / 卖出 0.03% + 0.1% 印花税 / 最低 5 元 全部通过 |

---

## 3. 端到端 API + 前端路由 (41/41 PASS)

### 3.1 系统与全局

| 用例 | HTTP | 说明 |
|------|------|------|
| GET /api/health | 200 | `app=股票数据库管理系统, v=1.0.0` |
| CORS 预检 (Origin=localhost:5173) | 200 | `Access-Control-Allow-Origin: *` |
| 异常脱敏 (error_id 字段) | 404 | 返回 `error_id=eaa0faa4c01d4f0e`,不泄漏堆栈 |
| 安全响应头 (5/5) | 200 | `x-content-type-options` / `x-frame-options` / `referrer-policy` / `content-security-policy` / `permissions-policy` 全部生效 |

### 3.2 鉴权 (`/api/auth`)

| 用例 | HTTP | 说明 |
|------|------|------|
| 错误密码 → 401 + 统一文案 | 401 | "账号或密码错误"(防账号枚举) |
| ctt 登录 → 200 | 200 | 同时下发 `tdj_access` / `tdj_refresh` / `tdj_csrf` 三个 cookie |
| GET /api/auth/me (cookie 鉴权) | 200 | 持久化登录可用 |
| 伪造 Bearer → 401 | 401 | JWT 验签失败 |
| 未登录 → 401 (deps) | 401 | 业务接口受 `require_admin` 保护 |

### 3.3 训练端 (`/api/train/*`)

| 用例 | HTTP | 说明 |
|------|------|------|
| POST /api/train/register | 200 | 动态创建用户,返回 access_token |
| POST /api/train/login | 200 | 训练端独立鉴权 |
| GET /api/train/me | 200 | `username` / `wallet_balance` 等字段齐全 |
| GET /api/train/wallet | 200 | `balance` / `total_spent` / `total_topup` |

### 3.4 股票 (`/api/stocks`)

| 用例 | HTTP | 说明 |
|------|------|------|
| GET /api/stocks (page=1) | 200 | total=5529, returned=5,数据库已存 5529 只 A 股 |
| GET /api/stocks?keyword=平安 | 200 | total=3,模糊搜索工作 |
| GET /api/stocks?market=sh | 200 | total=2309, all_sh=True,市场筛选正确 |
| GET /api/stocks/000001 | 200 | code=000001, kline_count=1210(平安银行详情) |
| GET /api/stocks/noexist → 404 | 404 | 统一 404 文案 |

### 3.5 K 线 (`/api/kline`)

| 用例 | HTTP | 说明 |
|------|------|------|
| GET /api/kline?code=000001 | 200 | total=1210 条日 K,返回 5 条明细 |
| GET /api/kline (日期范围 2026-01-01 ~ 2026-06-30) | 200 | 时间过滤正常 |
| GET /api/kline/indices?code=sh000001 | 200 | 指数 K 线查询 |

### 3.6 系统状态 (`/api/system`)

| 用例 | HTTP | 说明 |
|------|------|------|
| GET /api/system/status | 200 | `tables=['stock_list', 'kline_daily', 'index_daily', 'update_log', 'admin_user']` |
| GET /api/system/check | 200 | 健康检查通过 |

### 3.7 限速

| 用例 | HTTP | 说明 |
|------|------|------|
| 25 次错误登录 (`/api/auth/login`, 限速 10/min) | 429 | `401=5, 429=20` — slowapi 限速生效 |

### 3.8 前端 SPA 路由 + 静态资源 (`http://127.0.0.1:8000/`)

所有路径返回 200 且包含 `<title>`(证明 SPA index.html 兜底正确):

| 路径 | 路径 | 路径 |
|------|------|------|
| `/` | `/login` | `/admin` |
| `/train` | `/train/login` | `/dashboard` |
| `/stocks` | `/kline` | `/backtest` |
| `/tasks` | `/scheduler` | `/sources` |
| `/system` | `/strategies` | `/train/stats` |
| `/train/report` | `/assets/index-Bwmnp8S0.js` (chunk) | — |

---

## 4. 数据规模速览

| 表 | 行数 |
|----|-----:|
| `stock_list` | 5,529 |
| `kline_daily` | 6,143,838 |
| `index_daily` | 32,616 |
| `update_log` | 0 |
| `admin_user` | 2 |

> 库中已有 5529 只股票约 614 万条日 K 数据(约 3 年)。

---

## 5. 注意事项 / 待改进

1. **CORS 当前是 `*`** — 开发模式放行所有来源,生产前必须显式设置 `STOCK_CORS_ORIGINS=具体域名`。
2. **生产 SECRET_KEY** — 当前通过 `STOCK_DEV=1` 生成临时 key,部署前必须显式设置 `STOCK_SECRET_KEY`(≥32 字符)。
3. **登录失败锁定后** — 测试间通过 `scripts/reset_lock.py` 重置 `failed_attempts`;生产前可考虑关闭自动锁定或加 UI 重置入口。
4. **Windows GBK 编码** — `tests/test_system.py` 中 `print('  ✓ ...')` 在 PowerShell 默认编码下会抛 `UnicodeEncodeError`;需 `PYTHONIOENCODING=utf-8`(脚本里写有,但建议改成 `sys.stdout.reconfigure(encoding='utf-8')` 兜底)。
5. **未测试的接口** — 训练端 `/api/train/setup` / `/api/train/users` 等管理接口、`/api/backtest` 实际回测(因依赖 K 线数据且耗时较长)、`/api/scheduler` / `/api/sources` / `/api/tasks/update` 实际任务派发未在本次冒烟范围内,后续可按需追加。

---

## 6. 复测命令

```bash
# 启动后端(开发模式)
cd d:\AI\tradedojo\backend
$env:STOCK_DEV="1"; $env:PYTHONIOENCODING="utf-8"
uv run main.py      # 监听 :8000,自动托管 frontend/dist

# 单元测试(另一终端)
cd d:\AI\tradedojo\backend
$env:PYTHONIOENCODING="utf-8"
uv run python tests/test_system.py

# 全量端到端测试(后端运行后)
cd d:\AI\tradedojo
$env:PYTHONIOENCODING="utf-8"
uv run --directory backend python scripts/test_full_api.py
# 报告自动写到 d:\AI\tradedojo\TEST_REPORT.md
```

---

✅ **结论**:核心鉴权、限速、CSRF/Cookie、股票列表/搜索/筛选/详情、K线查询、系统状态、异常脱敏、安全头、CORS、限速、前端 SPA 路由全部通过。前端已构建并由后端直接托管。整套系统处于可演示状态。
