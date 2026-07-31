# TradeDojo 项目功能测试报告

- 报告时间: `2026-07-31T09:23:03`
- 后端地址: `http://127.0.0.1:8000`
- 运行模式: `STOCK_DEV=1`(开发模式)

## 汇总

- 通过: **41**
- 失败: **0**
- 总数: **41**

## 详细结果

| 类别 | 用例 | 状态 | HTTP | 备注 |
|------|------|------|------|------|
| system | GET /api/health | ✅ | 200 | app=股票数据库管理系统, v=1.0.0 |
| auth | 错误密码 → 401 + 统一文案 | ✅ | 401 |  |
| auth | ctt 登录 → 200 | ✅ | 200 |  |
| auth | GET /api/auth/me (cookie 鉴权) | ✅ | 200 |  |
| auth | 伪造 Bearer → 401 | ✅ | 401 |  |
| auth | 未登录 → 401 (deps) | ✅ | 401 |  |
| train | POST /api/train/register | ✅ | 200 |  |
| train | POST /api/train/login | ✅ | 200 |  |
| train | GET /api/train/me | ✅ | 200 |  |
| train | GET /api/train/wallet | ✅ | 200 |  |
| stocks | GET /api/stocks (page=1) | ✅ | 200 | total=5534, returned=5 |
| stocks | GET /api/stocks?keyword=平安 | ✅ | 200 | total=3 |
| stocks | GET /api/stocks?market=sh | ✅ | 200 | total=2310, all_sh=True |
| stocks | GET /api/stocks/000001 | ✅ | 200 | code=000001, kline_count=0 |
| stocks | GET /api/stocks/noexist → 404 | ✅ | 404 |  |
| kline | GET /api/kline?code=000001 | ✅ | 200 | total=0, items=0 |
| kline | GET /api/kline (date range) | ✅ | 200 |  |
| kline | GET /api/kline/indices?code=sh000001 | ✅ | 200 |  |
| system | GET /api/system/status | ✅ | 200 | tables=['stock_list', 'kline_daily', 'index_daily', 'update_log', 'admin_user'] |
| system | GET /api/system/check | ✅ | 200 |  |
| system | CORS 预检 (Origin=localhost:5173) | ✅ | 200 | acao=http://localhost:5173 |
| system | 异常脱敏 (error_id 字段) | ✅ | 404 | body[:80]={"code":404,"message":"股票 noexist 不存在","error_id":"af72b69233df4f9d"} |
| system | 安全响应头 (≥4/5 项) | ✅ | 200 | got=5/5  [x-content-type-options=True, x-frame-options=True, referrer-policy=True, content-security-policy=True, permissions-policy=True] |
| frontend | GET / | ✅ | 200 |  |
| frontend | GET /login | ✅ | 200 |  |
| frontend | GET /admin | ✅ | 200 |  |
| frontend | GET /train | ✅ | 200 |  |
| frontend | GET /train/login | ✅ | 200 |  |
| frontend | GET /dashboard | ✅ | 200 |  |
| frontend | GET /stocks | ✅ | 200 |  |
| frontend | GET /kline | ✅ | 200 |  |
| frontend | GET /backtest | ✅ | 200 |  |
| frontend | GET /tasks | ✅ | 200 |  |
| frontend | GET /scheduler | ✅ | 200 |  |
| frontend | GET /sources | ✅ | 200 |  |
| frontend | GET /system | ✅ | 200 |  |
| frontend | GET /strategies | ✅ | 200 |  |
| frontend | GET /train/stats | ✅ | 200 |  |
| frontend | GET /train/report | ✅ | 200 |  |
| frontend | GET /assets/*.js (chunk) | ✅ | 200 |  |
| system | 限速: 25 次错误登录 (限速 10/min) | ✅ | 429 | 401=5, 429=20 |
