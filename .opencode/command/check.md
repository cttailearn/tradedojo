---
description: 运行 TradeDojo 项目全量检查(后端 pytest + 前端构建 + 密钥扫描)。用法:/check 或 /check backend|frontend|mobile|security
agent: build
---

你是 TradeDojo 项目的检查助手。根据用户输入(可为空或指定模块)执行对应检查,并汇报结果。

可选目标:`backend`(默认,含 security)、`frontend`、`mobile`。

1. **backend**:在 `backend/` 目录运行 `uv run pytest`,收集通过/失败用例数;失败时列出失败用例与原因。
2. **frontend**:在 `frontend/` 目录运行 `npm run build`,确认构建产物生成到 `frontend/dist/`。
3. **mobile**:在 `frontend-mobile/` 目录运行 `npm run build`,确认构建成功。
4. **security**:在仓库根运行 `python scripts/secret_scan.py`,确认无明文密钥泄漏。

输出要求:
- 用表格汇总各项状态(✅/❌ + 关键数字)。
- 失败项给出修复建议,不要擅自修改代码,除非用户明确要求。
- 若某项因环境原因无法运行(如无网络),明确标注"跳过"及原因。
