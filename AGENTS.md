# AGENTS.md — TradeDojo 项目指南

本项目为 **A 股数据采集 + 回测训练管理系统**("操盘道场")。任何在该仓库工作的 agent 应先阅读本文件,理解架构、命令与约定后再动手。

## 技术栈总览

| 模块 | 技术 | 说明 |
|------|------|------|
| `backend/` | Python ≥3.10, FastAPI, Uvicorn, uv 管理 | API 服务 + SPA 托管,SQLite(WAL)存储 |
| `frontend/` | Vue 3 + Vite 5 + Element Plus + Pinia + ECharts | 桌面管理后台(股票/回测/任务/系统) |
| `frontend-mobile/` | Vue 3 + Vite 5 + Vant 4 + Tauri 2.0 + ECharts | 移动端训练 App(Android APK) |
| 数据源 | AKShare(主) / baostock / tushare 自动切换 | 日 K、指数、股票列表 |
| 部署 | Nginx + systemd + certbot,域名 cttai.art | 见 `deploy/README.md` |

## 目录结构(重要)

```
backend/
├── main.py            # Web 入口 (uv run main.py)
├── cli.py             # CLI 入口 (uv run tradedojo ...)
├── config.py          # 环境变量加载
├── app/               # FastAPI 应用
│   ├── main.py        # app 装配 + 安全头 + SPA 托管 + /api/* 与 /train/* 路由挂载
│   ├── config.py      # JWT/CORS/CSRF 配置
│   ├── auth.py        # JWT 签发/校验、refresh 旋转、UA 指纹绑定
│   ├── deps.py        # 依赖注入(admin/train 鉴权)
│   ├── database.py    # SQLite 连接与表结构
│   ├── task_manager.py# 内存后台任务(重启即丢)
│   ├── models.py      # Pydantic schema
│   └── routers/       # 业务路由:auth/train/stocks/kline/tasks/backtest/system/scheduler/sources/strategies 等
├── db/  fetcher/  updater/  backtest/   # 数据层:采集、更新、回测
├── tests/             # pytest 单元测试
├── data/  logs/       # SQLite 数据库与日志(不入库)
└── vendor/  Kronos-base/  # 大模型权重等大体积资源(不入库)

frontend/              # 管理后台 SPA
├── src/router/index.js        # hash 路由 + 鉴权守卫
├── src/api/                   # axios 实例 + 业务 API 封装
├── src/views/                 # Dashboard/Stocks/Kline/Tasks/Backtest/System/Scheduler/Sources/Strategies
└── src/views/train/           # 训练端页面(Home/Trade/Report/Stats/Wallet/UsersAdmin/RedeemAdmin)

frontend-mobile/       # 移动训练端(仅 /train/* 相关功能)
├── src/                       # Vant 移动组件,postcss-mobile-forever rem 适配(375 基准)
└── src-tauri/                 # Tauri 2 容器,Android APK 打包配置

deploy/                # Nginx/systemd/证书/备份脚本,见 deploy/README.md
scripts/               # 测试与运维脚本(test_*.py、backup_sqlite.py、secret_scan.py)
```

## 常用命令

```bash
# 后端
cd backend && uv sync                # 安装依赖
uv run main.py                       # 启动 API :8000(自动托管 frontend/dist)
uv run cli.py --help                 # CLI 数据采集
uv run pytest                        # 后端单元测试

# 管理前端
cd frontend && npm install
npm run dev                          # HMR :5173(代理 /api → :8000)
npm run build                        # 产物 frontend/dist/(后端直接托管)

# 移动端
cd frontend-mobile && npm install
npm run dev                          # Web 开发 :5174
npm run tauri:apk                    # 构建 Android APK

# 测试脚本(需后端已启动,STOCK_DEV=1 开发模式)
python scripts/test_full_api.py      # 全量 API 回归(见 TEST_REPORT.md)
python scripts/secret_scan.py        # 提交前扫描明文密钥
```

## 环境与配置约定

- 配置全部走环境变量(`.env`),由 `backend/config.py` 加载;模板见 `.env.example`。
- **生产强制**:`STOCK_SECRET_KEY`、`STOCK_ADMIN_PASSWORD` 未设置则拒绝启动。
- 本地开发:`STOCK_DEV=1` 自动生成临时密钥/管理员密码(写入 `logs/DEV_ADMIN_PASSWORD.txt`)。
- 凭据/密钥永不入库:`.env`、`*.tmp`、`admin_tok*`、`*_tok*`、`DEV_ADMIN_PASSWORD*` 已在 `.gitignore`。
- 修改配置类环境变量后需重启后端(systemd: `systemctl restart tradedojo`)。

## 代码约定

- 后端:FastAPI + Pydantic v2 风格;路由按模块拆分于 `app/routers/`;DB 操作走 `app/database.py` 的统一连接。
- 前端:Vue 3 Composition API + `<script setup>`;状态用 Pinia;接口调用统一走 `src/api/` 封装(自动附加 Bearer + CSRF 头)。
- 注释与文档:中文优先(README、代码注释均如此),提交信息用英文 conventional 风格(如 `feat(train): ...`、`fix(fetcher): ...`)。
- 新增依赖需同步更新 `backend/pyproject.toml`(uv lock)或对应 `package.json`。
- 大体积资源(模型权重等)放 `vendor/`、`Kronos-base/`,不入 git。

## 安全红线(改代码前必读 `SECURITY.md`)

- 鉴权:JWT(access + refresh 旋转)、登录限速、UA 指纹绑定;`/api/train/*` 走 Bearer,管理端走 httpOnly cookie + CSRF 双 cookie 校验。
- 响应头:安全头(5 项)由 `backend/app/main.py` 中间件统一设置,改动响应逻辑时勿破坏。
- 全局异常处理对外只暴露 `error_id`,日志过滤 Authorization/password/token。
- 训练端涉及用户钱包/兑换码/结算逻辑,修改时须跑 `scripts/test_full_api.py` 回归。

## 常见陷阱

- 后台任务(TaskManager)在内存中,重启丢失;调度器在主进程 threading 中跑,勿假设多 worker 场景。
- SQLite 仅适合单实例,数据库膨胀时清理 `update_log` 旧行并 `VACUUM`。
- 前端构建产物 `dist/` 不入库,但后端启动依赖其存在(不存在会自动降级或需先 build)。
- 修改 opencode 配置(`opencode.json`、`.opencode/`、AGENTS.md)后需重启 opencode 生效。
