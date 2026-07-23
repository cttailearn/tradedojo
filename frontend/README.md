# 前端 - 股票数据库管理系统

Vue 3 + Vite + Element Plus + Pinia 经典后台管理界面。

## 技术栈

| 层 | 选型 | 用途 |
|---|---|---|
| 框架 | Vue 3 (Composition API) | UI 框架,使用 `<script setup>` |
| 构建 | Vite 5 | 开发服务器 + 生产构建 |
| 路由 | Vue Router 4 | Hash 模式,适配任意后端托管 |
| 状态 | Pinia 2 | 鉴权状态(token / user) |
| UI | Element Plus | 表格/表单/对话框等组件 |
| 图表 | ECharts 5 | K线蜡烛图 + 成交量 |
| HTTP | Axios | 拦截器统一处理 token / 401 |

## 目录结构

```
frontend/
├── package.json              # 依赖 + npm scripts
├── vite.config.js            # dev proxy + build 配置
├── index.html                # SPA 入口
├── .gitignore
└── src/
    ├── main.js               # Vue 应用入口
    ├── App.vue               # 根组件 (router-view)
    ├── router/index.js       # 路由配置 + 守卫
    ├── stores/auth.js        # Pinia auth store
    ├── api/
    │   ├── index.js          # axios 实例 + 拦截器
    │   └── modules.js        # 业务 API 封装
    ├── layouts/
    │   └── AdminLayout.vue   # 左菜单 + 顶栏 + 内容区
    ├── views/                # 6 个页面 (单文件组件)
    │   ├── Login.vue
    │   ├── Dashboard.vue
    │   ├── Stocks.vue
    │   ├── Kline.vue
    │   ├── Tasks.vue
    │   ├── Backtest.vue
    │   └── System.vue
    └── styles/main.css       # 全局样式
```

## 启动方式

### 方式 A: 开发模式(推荐)

```bash
# 终端 1:启动后端
cd backend
uv sync
uv run main.py              # 监听 :8000

# 终端 2:启动前端开发服务器
cd frontend
npm install
npm run dev                 # 监听 :5173,HMR + API 代理到 8000
```

访问 <http://localhost:5173> — Vite 自动代理 `/api/*` 到后端。

### 方式 B: 生产模式(后端托管构建产物)

```bash
# 1. 构建前端
cd frontend
npm install
npm run build               # 输出到 frontend/dist/

# 2. 启动后端(自动托管 dist/)
cd ../backend
uv run main.py              # 监听 :8000
```

访问 <http://localhost:8000> — 后端把 `dist/index.html` 作为 SPA 入口。

## 默认账号

```
用户名: admin
密码:   admin123
```

## 路由结构

| 路径 | 组件 | 说明 |
|------|------|------|
| `/login` | Login | 登录页(无需 token) |
| `/dashboard` | Dashboard | 仪表盘 |
| `/stocks` | Stocks | 股票管理 |
| `/kline` | Kline | K线查询 |
| `/tasks` | Tasks | 数据更新 |
| `/backtest` | Backtest | 回测中心 |
| `/system` | System | 系统状态 |

所有业务路由都需要登录,通过 `router.beforeEach` 守卫强制鉴权。

## 与后端的集成

- 开发模式:Vite 代理 `/api/*` → `http://127.0.0.1:8000`
- 生产模式:相对路径 `/api/*`,由 FastAPI 同源服务
- 鉴权:localStorage 存 token,axios 拦截器自动加 `Authorization: Bearer <token>`
- 401 处理:拦截器自动清 token + 跳转 `/login`

## 常用命令

```bash
npm run dev       # 开发服务器(HMR)
npm run build     # 生产构建(输出到 dist/)
npm run preview   # 本地预览构建产物
```