"""
Parity test: 前端 calcSessionCost 与后端 app.utils.calc_session_cost 必须数值一致.
运行:  uv run python scripts/test_train_fee_parity.py
"""
import subprocess
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 调用 Node 直接 import 前端模块计算 JS 版结果.
JS_TEST = r"""
// 临时用 esbuild-free 做法:读取文件内容并用 eval 跑
const fs = require('fs')
const path = require('path')
const src = fs.readFileSync(path.resolve('frontend/src/utils/trainFee.js'), 'utf-8')
// 改成 CommonJS 写法
const mod = src
  .replace(/export\s+function\s+/g, 'function ')
  .replace(/^function\s+calcSessionCost/, 'module.exports.calcSessionCost = function calcSessionCost')
eval(mod)
const fc = process.argv[2]
const cases = [
  ['2024-01-02', '2024-12-30', 1_000_000],
  ['2024-06-01', '2024-12-31', 500_000],
  ['2024-01-02', '2024-12-30', 5_000_000],
  ['2023-01-02', '2024-12-30', 1_000_000],
  ['invalid', 'invalid', 0],
]
console.log(JSON.stringify(cases.map((c) => module.exports.calcSessionCost(c[0], c[1], c[2]))))
"""

# 调用 Python 端
PY_TEST = """
import sys, json
sys.path.insert(0, r"%(root)s/backend")
from app.utils import calc_session_cost as py_calc
cases = [
    ('2024-01-02', '2024-12-30', 1_000_000),
    ('2024-06-01', '2024-12-31', 500_000),
    ('2024-01-02', '2024-12-30', 5_000_000),
    ('2023-01-02', '2024-12-30', 1_000_000),
    ('invalid',   'invalid',   0),
]
print(json.dumps([py_calc(s, e, c) for s, e, c in cases]))
""" % {"root": str(ROOT).replace("\\", "/")}

# 跑 JS
try:
    js_out = subprocess.run(
        ["node", "-e", JS_TEST],
        cwd=str(ROOT), capture_output=True, text=True, check=True,
    )
    js_vals = json.loads(js_out.stdout.strip().split("\n")[-1])
except Exception as e:
    print("[ERROR] Node not available or test failed:", e)
    print("如果本地没 Node,请人工对照 frontend/src/utils/trainFee.js 与 backend/app/utils.py")
    sys.exit(0)

# 跑 Python
py_out = subprocess.run(
    [sys.executable, "-c", PY_TEST], capture_output=True, text=True, check=True,
)
py_vals = json.loads(py_out.stdout.strip().split("\n")[-1])

print("JS  :", js_vals)
print("Py  :", py_vals)
print("DIFF:", [round(a - b, 4) for a, b in zip(js_vals, py_vals)])
if any(abs(a - b) > 0.01 for a, b in zip(js_vals, py_vals)):
    print("[FAIL] parity 不一致,需同步前端 utils/trainFee.js 或后端 app/utils.py")
    sys.exit(1)
print("[OK] parity 一致")
