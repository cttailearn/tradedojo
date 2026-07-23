# TradeDojo · 操盘道场

> **A 股数据采集 + 回测训练管理系统** — 反复操练交易技术的道场
>
> English: **TradeDojo** — A share data collection & backtesting training system
>
> **FastAPI + uv** 后端 · **Vue 3 + Vite** 前端 · AKShare 数据源 · SQLite 存储

## 📁 目录结构

```
stock_data_system/
├── backend/                          # FastAPI 后端 (uv 管理)
│   ├── pyproject.toml                # 依赖声明
│   ├── uv.lock
│   ├── main.py                       # Web 入口 (uv run main.py)
│   ├── cli.py                        # CLI 入口 (uv run cli.py)
│   ├── run.sh / start.bat
│   ├── config.py
│   ├── app/                          # FastAPI 应用代码
│   │   ├── main.py                   # FastAPI app + SPA 托管
│   │   ├── config.py                 # JWT/CORS/路径
│   │   ├── database.py               # admin_user 表
│   │   ├── auth.py / deps.py         # JWT
│   │   ├── task_manager.py           # 后台任务
│   │   ├── models.py                 # Pydantic schema
│   │   └── routers/                  # 6 个业务路由
│   ├── db/  fetcher/  updater/  backtest/   # 数据采集
│   ├── tests/test_system.py          # 8 个单元测试
│   ├── scripts/                      # demo 脚本
│   ├── data/                         # SQLite
│   └── logs/
│
├── frontend/                         # Vue 3 前端 (Vite 构建)
│   ├── package.json
│   ├── vite.config.js                # dev proxy + build 配置
│   ├── index.html
│   ├── src/
│   │   ├── main.js                   # Vue 入口
│   │   ├── App.vue
│   │   ├── router/index.js           # Vue Router (hash 模式)
│   │   ├── stores/auth.js            # Pinia
│   │   ├── api/                      # axios 封装 + 业务模块
│   │   ├── layouts/AdminLayout.vue   # 左菜单 + 内容
│   │   ├── views/                    # 6 个 SFC 页面
│   │   └── styles/main.css
│   └── dist/                         # npm run build 输出
│
├── .gitignore
└── README.md
```

## ✨ 功能(交易训练专用)

本项目定位为「交易技术训练道场」,围绕「反复练、复盘、对比」三个动作展开:

- **管理界面** - 浏览器访问,左侧菜单 + 右侧内容
- **管理员登录** - JWT 鉴权,默认 `admin / admin123`
- **股票管理** - 分页 / 关键词 / 市场 / 行业筛选 / 详情
- **K线查询** - 单股查询 + ECharts 蜡烛图 + 明细表
- **数据更新** - 后台任务派发 + 实时日志轮询 + 断点重置
- **回测中心** - 单股 + 组合,SMA / 动量 / 买入持有三种策略
- **系统状态** - 表行数 / 缺失检查 / 日志在线查看

## 🚀 快速开始

### 1. 启动后端

```bash
cd backend
uv sync
uv run main.py             # 监听 :8000,自动托管 frontend/dist/
```

### 2. 构建前端(首次)

```bash
cd frontend
npm install
npm run build              # 输出到 dist/
```

> 后端启动时会自动加载 `frontend/dist/`,无需单独跑前端。

### 3. 开发模式(可选)

如果想修改前端代码并热更新:

```bash
# 终端 1
cd backend && uv run main.py

# 终端 2
cd frontend && npm run dev   # 监听 :5173,Vite 代理 /api -> :8000
```

访问 <http://localhost:5173>

## 📊 API (25 个端点)

| 模块 | 关键端点 |
|------|----------|
| 认证 | `POST /api/auth/login` · `GET /api/auth/me` |
| 股票 | `GET /api/stocks` · `GET /api/stocks/{code}` |
| K线 | `GET /api/kline` · `GET /api/kline/indices` |
| 更新 | `POST /api/tasks/update` · `GET /api/tasks/{id}` |
| 回测 | `POST /api/backtest` · `POST /api/backtest/portfolio` |
| 系统 | `GET /api/system/status` · `GET /api/system/check` |

## 🛠 技术栈

**后端**
- FastAPI + Uvicorn
- python-jose (JWT)
- AKShare (数据源)
- Backtrader (回测)
- SQLite + WAL
- uv (依赖管理)

**前端**
- Vue 3 (Composition API + `<script setup>`)
- Vite 5 (开发 + 构建)
- Vue Router 4 (Hash 模式)
- Pinia 2 (状态管理)
- Element Plus (UI)
- ECharts (K线图)
- Axios

## ⚠️ 注意事项

1. **数据源合规** - AKShare 仅供学习研究
2. **生产部署** - 修改 `SECRET_KEY`,关闭 `CORS=*`
3. **首次全量** - 5 年日 K 全市场约 60 分钟
4. **定期备份** - `backend/data/stock.db`