"""
K线交易训练 —— 业务主路由
- 随机选股 / 开训练场
- 时间推进(逐日揭示 K 线)
- 下单撮合(买入/卖出)
- 持仓 / 资金 / 成交记录
"""
import logging
import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.deps_train import get_current_train_user
from app.models import (
    AdvanceRequest,
    TradeOrderRequest,
    TrainingSetupRequest,
)
from app.rate_limit import limiter
from app.utils import calc_session_cost
from db.database import (
    user_execute as execute,
    get_user_conn as get_conn,
    user_query_all as query_all,
    user_query_one as query_one,
    # 训练路由内还要查 stock 库:
    query_all as stock_query_all,
    query_one as stock_query_one,
)


log = logging.getLogger("app.train.trade")

router = APIRouter(prefix="/api/train", tags=["训练端-交易"],
                   dependencies=[Depends(get_current_train_user)])


# =========================================================
# Helpers
# =========================================================
def _pick_random_stock(req: TrainingSetupRequest) -> dict:
    """根据训练参数随机挑一只符合过滤条件的股票.

    重写为两步走,避免 ORDER BY RANDOM() + 大表 JOIN 的全表扫:
      1. 用相同 where 拿到候选 code 列表(只查 stock_list,小表快);
      2. 随机选 1 个 code,单独校验 K 线覆盖度与 ST 状态;
      3. 不合格就再随机一个,最多 5 次,降级挑最宽松的版本.

    2026-08-04 分钟级: bar_period in (30, 60) 时校验对象改为 kline_minute
    (code+period),避免随机选到无分钟数据的股票导致 start 400。
    """
    period = _session_period({"bar_period": req.bar_period})
    is_minute = period in (30, 60)
    where = ["s.is_active = 1"]
    params = []
    if not req.allow_chinext:
        where.append("s.code NOT LIKE '30%'")
    if not req.allow_kcb:
        where.append("s.code NOT LIKE '688%'")
    if not req.allow_bj:
        where.append("s.code NOT LIKE '8%' AND s.code NOT LIKE '92%'")
    if req.market:
        where.append("s.market = ?"); params.append(req.market)
    if req.industry:
        where.append("s.industry = ?"); params.append(req.industry)
    if req.keyword:
        where.append("(s.code LIKE ? OR s.name LIKE ?)")
        kw = f"%{req.keyword}%"
        params.extend([kw, kw])

    base_where_sql = ' AND '.join(where)
    # Step 1: 拉候选(只查 stock_list,带可见字段)—— 通常几千行,几乎瞬间
    if is_minute:
        # 分钟模式(2026-08-12): 候选收敛到"有日K线"的股票即可 ——
        # 分钟K由日K确定性合成(_minute_bars 回退),不再依赖 kline_minute 表。
        base_where_sql += (
            " AND s.code IN (SELECT DISTINCT code FROM kline_daily WHERE adjust_type = 'qfq')"
        )
    rows = stock_query_all(
        f"SELECT s.code, s.name, s.industry, s.market FROM stock_list s "
        f"WHERE {base_where_sql} ORDER BY s.code ASC",
        tuple(params),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="没有符合条件的股票(请放宽过滤)")
    random.shuffle(rows)

    def _has_enough_kline(code: str) -> bool:
        # 日K覆盖即满足(分钟模式由日K合成, 与日线共用同一判据)
        cnt = stock_query_one(
            "SELECT COUNT(*) FROM kline_daily "
            "WHERE code = ? AND adjust_type = 'qfq' "
            "  AND trade_date <= ?",
            (code, req.end_date),
        )
        if not cnt:
            return False
        n = cnt[0] or 0
        if n >= req.lookback_months * 20:
            return True
        # 宽松模式: 至少 5 根
        return n >= 5

    attempts = 0
    for code, name, industry, market in rows:
        if attempts >= 5:
            break
        attempts += 1
        # ST 过滤(只能事后检查 name): 严格要求"非 ST"才进
        n_up = (name or "").upper()
        if not req.allow_st and ("ST" in n_up or "*ST" in n_up):
            continue
        if not _has_enough_kline(code):
            continue
        if is_minute:
            # 分钟模式: 区间内存在分钟K线即可(上面已校验),无需再查日线 MIN/MAX
            return {"code": code, "name": name, "industry": industry, "market": market}
        # 还要求区间内全部存在(训练区间被节假日/退市切片):
        # 用 1 次 SELECT 看下 MIN/MAX
        rng = stock_query_one(
            "SELECT MIN(trade_date), MAX(trade_date) FROM kline_daily "
            "WHERE code = ? AND adjust_type = 'qfq'",
            (code,),
        )
        if not rng or not rng[1]:
            continue
        if rng[1] < req.start_date:
            continue
        return {"code": code, "name": name, "industry": industry, "market": market}

    # 降级:第一个候选(允许 K 线不足或非交易日)
    code, name, industry, market = rows[0]
    return {"code": code, "name": name, "industry": industry, "market": market}


def _session_period(sess: dict) -> int:
    """返回会话 K 线周期:240=日线(默认), 30/60=分钟。
    bar_period 缺失(旧数据)或解析失败一律视为 240, 保证日线零回归。
    """
    try:
        v = int(sess.get("bar_period") or 240)
    except Exception:
        v = 240
    return v


# =====================================================================
# 合成分钟 K 线(2026-08-12)
#
# 背景: 分钟级训练依赖 kline_minute 真实数据, 但当前库中该表为空,
# 且 sina 数据源不稳定、历史仅约 1 年。为让 30/60 分钟训练立即可用,
# 增加"由日 K 确定性合成分钟 K"的能力(不落库, 训练期间内存生成)。
#
# 确定性原则: 同一 (code, period, trade_date) 每次都生成完全相同的
# 分钟 bar —— 因为交易撮合/风控/展示都必须看到同一份数据。
# seed = stable hash(code|period|trade_date)。
# =====================================================================

# 每个交易日的分钟 bar 数(A 股 4 小时)
_MINUTE_BARS_PER_DAY = {30: 8, 60: 4}
# 每个 bar 的起始时间(30 分: 09:30,10:00,10:30,11:00,13:00,13:30,14:00,14:30)
# (60 分: 09:30,10:30,13:00,14:00) —— 与常见行情终端一致
_MINUTE_TIMES = {
    30: ["09:30", "10:00", "10:30", "11:00", "13:00", "13:30", "14:00", "14:30"],
    60: ["09:30", "10:30", "13:00", "14:00"],
}


def _stable_seed(code: str, period: int, trade_date: str) -> int:
    """生成稳定种子: 同 (code, period, date) → 同 seed, 保证可复现。"""
    import hashlib
    h = hashlib.sha256(f"{code}|{period}|{trade_date}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _synthesize_minute_bars(daily: dict, period: int) -> list[dict]:
    """由单根日 K 确定性合成一根交易日内的分钟 bar 列表。

    daily: kline_daily 一行, 含 trade_date/open/high/low/close/volume/amount。
    算法(简单、稳定):
      - 价格: 从 open 出发按比例走向 close, 每根 bar 的 OHLC 在 [low, high] 内
        用正态噪声扰动; 整日高低点恰好出现在某根 bar(保证 high/low 被覆盖)。
      - 成交量: 按 U 型分布(开盘/收盘放量)分配日成交量。
      - amount: 同比例分配(缺失则 None)。
    返回: 与 _kline_in_window 分钟分支同构的 dict 列表。
    """
    import random as _rng
    n = _MINUTE_BARS_PER_DAY[period]
    times = _MINUTE_TIMES[period]
    date = daily["trade_date"]
    o, h, l, c = daily["open"], daily["high"], daily["low"], daily["close"]
    vol = daily.get("volume") or 0
    amt = daily.get("amount")

    rng = _rng.Random(_stable_seed(daily["code"], period, date))

    # 基础走向: open -> close 的线性插值
    base = [o + (c - o) * (i / (n - 1)) for i in range(n)] if n > 1 else [o]
    # 确定性噪声(幅度 ~ 日内振幅的 12%)
    amp = max(float(h or 0) - float(l or 0), abs(float(c or 0) - float(o or 0)), 0.01)
    noise = [rng.uniform(-0.12, 0.12) * amp for _ in range(n)]
    prices = [base[i] + noise[i] for i in range(n)]
    # 固定两端: 首 bar open=日 open, 末 bar close=日 close
    prices[0] = float(o)
    prices[-1] = float(c)
    # 钳制到 [low, high]
    prices = [max(float(l), min(float(h), p)) for p in prices]
    # 保证高低点覆盖: 最低价给振幅最低的 bar, 最高价给振幅最高的 bar
    lo_idx = min(range(n), key=lambda i: prices[i])
    hi_idx = max(range(n), key=lambda i: prices[i])
    prices[lo_idx] = float(l)
    prices[hi_idx] = float(h)
    # 两端仍保持 open/close
    prices[0] = float(o)
    prices[-1] = float(c)

    # U 型成交量权重(30分 8 根 / 60分 4 根)
    if n == 8:
        w = [1.6, 1.2, 1.0, 0.9, 0.9, 1.0, 1.2, 1.6]
    else:
        w = [1.5, 0.9, 0.9, 1.5]
    wsum = sum(w)

    out = []
    for i in range(n):
        p = prices[i]
        # 每根 bar 的 open/close: 中间 bar 用相邻价格, 首根 open=日open, 末根 close=日close
        bar_open = float(o) if i == 0 else prices[i - 1]
        bar_close = float(c) if i == n - 1 else prices[i]
        # high/low: 围绕该 bar 价格加小幅噪声, 但不超过日 high/low
        bh = min(float(h), max(bar_open, bar_close) + rng.uniform(0, 0.02) * amp)
        bl = max(float(l), min(bar_open, bar_close) - rng.uniform(0, 0.02) * amp)
        # 若该 bar 恰好是日高/日低, 保证覆盖
        if i == hi_idx:
            bh = float(h)
        if i == lo_idx:
            bl = float(l)
        v = int(vol * w[i] / wsum) if vol else 0
        out.append({
            "trade_date": date,
            "trade_time": f"{date} {times[i]}:00",
            "open": round(bar_open, 4),
            "high": round(bh, 4),
            "low": round(bl, 4),
            "close": round(bar_close, 4),
            "volume": v,
            "amount": round(amt * w[i] / wsum, 2) if amt is not None else None,
            "pre_close": None,
            "change_amount": 0,
            "pct_change": 0,
            "turnover_rate": None,
        })
    return out


def _minute_bars(
    code: str,
    period: int,
    start_dt: str,
    end_dt: str,
    order: str = "ASC",
    limit: Optional[int] = None,
) -> list[dict]:
    """分钟 K 线统一访问层(30/60 分)。

    优先读 kline_minute 真实数据; 无数据(表空/该股无分钟数据)时
    回退到从 kline_daily 合成 —— 保证分钟训练在无真实分钟数据时也可用。

    start_dt/end_dt: trade_time 的边界(如 "2026-07-01" 或 "2026-07-01 13:00:00")。
    返回: [{trade_time, open, high, low, close, volume, amount, ...}] 升序。
    """
    rows = stock_query_all(
        "SELECT trade_time, open, high, low, close, volume, amount "
        "FROM kline_minute "
        "WHERE code = ? AND period = ? AND trade_time >= ? AND trade_time <= ? "
        "ORDER BY trade_time " + order + (f" LIMIT {int(limit)}" if limit else ""),
        (code, period, start_dt, end_dt),
    )
    if rows:
        return [{
            "trade_date": r[0][:10], "trade_time": r[0],
            "open": r[1], "high": r[2], "low": r[3],
            "close": r[4], "volume": r[5], "amount": r[6],
            "pre_close": None, "change_amount": 0, "pct_change": 0,
            "turnover_rate": None,
        } for r in rows]

    # ---- 回退: 由日 K 合成 ----
    # 找出 [start 日, end 日] 内的日 K(仅 qfq, 与日线训练一致)
    start_day = start_dt[:10]
    end_day = end_dt[:10]
    daily_rows = stock_query_all(
        "SELECT trade_date, open, high, low, close, volume, amount "
        "FROM kline_daily "
        "WHERE code = ? AND adjust_type = 'qfq' "
        "  AND trade_date >= ? AND trade_date <= ? "
        "ORDER BY trade_date ASC",
        (code, start_day, end_day),
    )
    out = []
    for r in daily_rows:
        daily = {
            "code": code, "trade_date": r[0], "open": r[1], "high": r[2],
            "low": r[3], "close": r[4], "volume": r[5], "amount": r[6],
        }
        out.extend(_synthesize_minute_bars(daily, period))
    # 按 trade_time 过滤边界(合成基于整日, 可能包含 start_dt 之前/end_dt 之后的时间)
    out = [b for b in out if b["trade_time"] >= start_dt and b["trade_time"] <= end_dt]
    if order == "DESC":
        out.reverse()
    if limit:
        out = out[:limit]
    return out


def _kline_in_window(code: str, start_date: str, end_date: str, period: int = 240) -> list:
    """读取某只股票在 [start, end] 区间的 K 线 (stock.db)。

    2026-08-04 分钟级: period in (30, 60) 走 _minute_bars(优先真实
    kline_minute, 无则从日 K 合成, 2026-08-12)。
    返回结构与日线同构(多带 trade_time 完整时间戳)。
    """
    if period in (30, 60):
        return _minute_bars(
            code, period,
            f"{start_date} 00:00:00",
            f"{end_date} 23:59:59",
        )
    rows = stock_query_all(
        """SELECT trade_date, open, high, low, close, pre_close,
                  change_amount, pct_change, volume, amount, turnover_rate
           FROM kline_daily
           WHERE code = ? AND adjust_type = 'qfq'
             AND trade_date >= ? AND trade_date <= ?
           ORDER BY trade_date ASC""",
        (code, start_date, end_date),
    )
    return [{
        "trade_date": r[0], "open": r[1], "high": r[2], "low": r[3],
        "close": r[4], "pre_close": r[5], "change_amount": r[6],
        "pct_change": r[7], "volume": r[8], "amount": r[9],
        "turnover_rate": r[10],
    } for r in rows]


# 2026-08-04 分钟级: 必须与 training_session 的 SELECT * 实际列序一致。
# 实测(迁移库 PRAGMA 确认):reveal_time/bar_period 由 ensure_col 以
# ALTER TABLE ADD COLUMN 追加在末尾(auto_stop_* 后),而非 schema.sql 的
# 全新建表顺序。日线回归:created_at/updated_at/auto_stop_* 均按该顺序对齐。
SESSION_COLS = (
    # 与 PG training_session 实际列序一致(2026-08-12 修正):
    # auto_stop_loss_pct/auto_take_profit_pct 位于 created_at/updated_at 之前,
    # 此前顺序颠倒导致 dict(zip(SESSION_COLS, row)) 字段错位,
    # 使 _check_risk_rules 的 float(auto_stop_loss_pct) 拿到时间戳而崩溃。
    "id", "user_id", "code", "name", "industry", "market",
    "start_date", "end_date", "lookback_months", "initial_cash",
    "commission_rate", "min_commission", "stamp_tax", "transfer_fee",
    "allow_split", "max_positions", "per_trade_amount", "allow_chinext",
    "allow_st", "allow_kcb", "allow_bj", "total_fee_paid", "status",
    "reveal_date",
    "auto_stop_loss_pct", "auto_take_profit_pct",
    "created_at", "updated_at",
    "bar_period", "reveal_time",
)


def _session_for_user(user_id: int, session_id: int) -> dict:
    row = query_one(
        "SELECT * FROM training_session WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="训练会话不存在")
    return dict(zip(SESSION_COLS, row))


def _fifo_cost_basis(user_id: int, session_id: int, sell_qty: int) -> tuple[float, float]:
    """FIFO 计算本次卖出对应的成本基础(从所有 BUY 订单按时间顺序消耗);
    返回 (cost_basis, fee_proportion)
    """
    rows = query_all(
        "SELECT id, quantity, price, commission, stamp_tax, transfer_fee, total_fee "
        "FROM training_order "
        "WHERE user_id = ? AND session_id = ? AND side = 'BUY' "
        "ORDER BY trade_date ASC, id ASC",
        (user_id, session_id),
    )
    cost_basis = 0.0
    fee_proportion = 0.0  # 卖出时按卖股数 / 原始买股数 比例分摊买入费用
    remaining = sell_qty
    for _id, qty, price, commission, stamp_tax, transfer_fee, total_fee in rows:
        if remaining <= 0:
            break
        take = min(qty, remaining)
        cost_basis += take * price
        # 按比例分摊买入时的手续费(影响实现盈亏的精确度)
        fee_proportion += (total_fee or 0) * (take / qty)
        remaining -= take
    return cost_basis, fee_proportion


def _calc_total_fees(amount: float, qty: int, session: dict, side: str) -> dict:
    """计算买入/卖出的手续费(人民币)"""
    commission = max(amount * session["commission_rate"], session["min_commission"])
    stamp_tax = amount * session["stamp_tax"] if side == "SELL" else 0.0
    transfer_fee = amount * session["transfer_fee"]
    total = commission + stamp_tax + transfer_fee
    return {
        "commission": round(commission, 2),
        "stamp_tax": round(stamp_tax, 2),
        "transfer_fee": round(transfer_fee, 2),
        "total_fee": round(total, 2),
    }


def _wallet_for_update(user_id: int) -> float:
    """在事务里扣减/增加钱包余额的辅助"""
    row = query_one("SELECT balance FROM training_wallet WHERE user_id = ?", (user_id,))
    if row is None:
        execute("INSERT INTO training_wallet(user_id, balance) VALUES(?, 0)", (user_id,))
        return 0.0
    return float(row[0] or 0)


def _wallet_for_update_in_conn(conn, user_id: int) -> float:
    """在事务连接里读 wallet 余额,不存在则插入"""
    row = conn.execute(
        "SELECT balance FROM training_wallet WHERE user_id = ?", (user_id,),
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO training_wallet(user_id, balance) VALUES(?, 0)", (user_id,),
        )
        return 0.0
    return float(row[0] or 0)


def _wallet_balance(user_id: int) -> float:
    """非事务读:返回当前钱包余额"""
    row = query_one("SELECT balance FROM training_wallet WHERE user_id = ?", (user_id,))
    if row is None:
        execute("INSERT INTO training_wallet(user_id, balance) VALUES(?, 0)", (user_id,))
        return 0.0
    return float(row[0] or 0)


def _build_session_view(session: dict) -> dict:
    """基于数据库拼装完整的会话视图(用于前端)"""
    sid = session["id"]
    code = session["code"]
    user_id = session["user_id"]

    # 已揭示 K 线:
    #   - 从 session.start_date - lookback_months(历史回看)开始
    #   - 到 current_date(逐日推进揭示到这里)为止
    from datetime import datetime as _dt
    period = _session_period(session)
    is_minute = period in (30, 60)
    # 分钟模式:current_dt 用 reveal_time 精确到 bar;日线模式用 reveal_date
    current_dt = (
        session.get("reveal_time")
        if is_minute and session.get("reveal_time")
        else (session.get("reveal_date") or session["start_date"])
    )
    try:
        sd = _dt.strptime(session["start_date"], "%Y-%m-%d").date()
        # 历史回看月份
        year = sd.year - (session["lookback_months"] // 12)
        month = sd.month - (session["lookback_months"] % 12)
        while month <= 0:
            month += 12
            year -= 1
        lookback_start = f"{year:04d}-{month:02d}-{sd.day:02d}"
    except Exception:
        lookback_start = session["start_date"]
    revealed = _kline_in_window(code, lookback_start, current_dt, period)
    # 分钟模式的 current_dt 已精确到特定 bar,末尾已恰好为揭示 bar;
    # "reveal_date 非交易日顺延下一根" 逻辑仅保留日线模式(分钟模式跳过)。
    if period == 240 and revealed and revealed[-1]["trade_date"] < current_dt:
        next_bar = _kline_in_window(code, current_dt, "2099-12-31", period)
        if next_bar:
            revealed = revealed + [next_bar[0]]
    current_bar = revealed[-1] if revealed else None
    # 统一给 current_bar 附上 trade_time(分钟模式为完整时间戳,日线为 None)
    if current_bar is not None and "trade_time" not in current_bar:
        current_bar = {**current_bar, "trade_time": None}

    # 2026-07-31 优化: 当前 bar 的涨跌停区间(供前端展示可成交价区间)
    price_limit = None
    if current_bar:
        pre_close = float(current_bar.get("pre_close") or 0) or None
        if not pre_close and revealed and len(revealed) >= 2:
            pre_close = float(revealed[-2].get("close") or 0)
        if pre_close and pre_close > 0:
            price_limit = _calc_price_limit(
                code, session.get("name") or "", pre_close,
            )

    # 持仓
    pos_rows = query_all(
        "SELECT code, quantity, avg_cost FROM training_position "
        "WHERE session_id = ? ORDER BY code",
        (sid,),
    )
    positions = []
    market_value = 0.0
    for c, qty, avg_cost in pos_rows:
        cur_price = current_bar["close"] if current_bar and c == code else None
        if cur_price is not None:
            mv = qty * cur_price
            market_value += mv
        else:
            mv = qty * (avg_cost or 0)
        positions.append({
            "code": c, "quantity": qty, "avg_cost": avg_cost,
            "current_price": cur_price,
            "market_value": round(mv, 2),
            "float_pnl": round((cur_price - avg_cost) * qty, 2) if cur_price else 0,
            "float_pnl_pct": round(((cur_price / avg_cost) - 1) * 100, 2)
                if cur_price and avg_cost else 0,
        })

    # 现金:与钱包共享(共用资金),直接读 wallet.balance
    orders = query_all(
        "SELECT id, trade_date, side, price, quantity, amount, "
        "       commission, stamp_tax, transfer_fee, total_fee, realized_pnl "
        "FROM training_order WHERE session_id = ? ORDER BY id DESC LIMIT 50",
        (sid,),
    )
    cash = _wallet_balance(user_id)
    total_equity = cash + market_value

    recent_orders = [{
        "id": o[0], "trade_date": o[1], "side": o[2], "code": code,
        "price": o[3], "quantity": o[4], "amount": o[5],
        "commission": o[6], "stamp_tax": o[7], "transfer_fee": o[8],
        "total_fee": o[9], "realized_pnl": o[10],
    } for o in orders]

    return {
        "id": sid,
        "code": code,
        "name": session.get("name"),
        "industry": session.get("industry"),
        "market": session.get("market"),
        "start_date": session["start_date"],
        "end_date": session["end_date"],
        "current_date": current_dt,
        "bar_period": period,
        "reveal_time": session.get("reveal_time"),
        "lookback_months": session["lookback_months"],
        "initial_cash": session["initial_cash"],
        "status": session["status"],
        "cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "total_equity": round(total_equity, 2),
        "total_pnl": round(total_equity - session["initial_cash"], 2),
        "total_pnl_pct": round((total_equity / session["initial_cash"] - 1) * 100, 2),
        "positions": positions,
        "recent_orders": recent_orders,
        "current_bar": current_bar,
        "revealed_bars": revealed,
        "fee_rules": {
            "commission_rate": session["commission_rate"],
            "min_commission": session["min_commission"],
            "stamp_tax": session["stamp_tax"],
            "transfer_fee": session["transfer_fee"],
            "allow_split": session["allow_split"],
            "max_positions": session["max_positions"],
            "per_trade_amount": session["per_trade_amount"],
        },
        "price_limit": price_limit,  # 2026-07-31 优化: 涨跌停区间
    }


def _calc_price_limit(code: str, name: str, pre_close: float) -> dict:
    """计算股票当日涨跌停范围(2026-07-31 优化)。
    创业板(30x)/科创板(688) ±20%, ST ±5%, 其他 ±10%。
    返回 {upper, lower, limit_pct, is_st, is_chinext, is_kcb}。
    """
    name_u = (name or "").upper()
    is_st = "ST" in name_u
    is_chinext = (code or "").startswith("30")
    is_kcb = (code or "").startswith("688")
    if is_chinext or is_kcb:
        limit_pct = 0.20
    elif is_st:
        limit_pct = 0.05
    else:
        limit_pct = 0.10
    return {
        "upper": round(pre_close * (1 + limit_pct), 2),
        "lower": round(pre_close * (1 - limit_pct), 2),
        "limit_pct": limit_pct,
        "is_st": is_st,
        "is_chinext": is_chinext,
        "is_kcb": is_kcb,
    }


def _check_risk_rules(sess: dict, advance_dates: list, user_id: int, period: int = 240) -> list:
    """2026-07-31 P2-3 优化: 自动风控规则 - 止损/止盈触发后自动市价单成交。
    返回触发的 [{type, code, qty, price, pnl_pct, date}], 无触发返回 []。
    """
    stop_pct = float(sess.get("auto_stop_loss_pct") or 0)
    take_pct = float(sess.get("auto_take_profit_pct") or 0)
    if stop_pct <= 0 and take_pct <= 0:
        return []
    if not advance_dates:
        return []

    code = sess["code"]
    # 拉持仓
    pos_row = query_one(
        "SELECT quantity, avg_cost FROM training_position "
        "WHERE session_id = ? AND code = ?",
        (sess["id"], code),
    )
    if not pos_row or pos_row[0] <= 0:
        return []
    qty = int(pos_row[0])
    avg_cost = float(pos_row[1] or 0)
    if avg_cost <= 0:
        return []

    # 拉 advance 期间的 bar, 找首个触发日
    # 分钟模式用 _minute_bars(真实数据优先, 无则日K合成);日线模式查 kline_daily。
    if period in (30, 60):
        if advance_dates:
            bars = [
                (b["trade_time"], b["open"], b["high"], b["low"], b["close"])
                for b in _minute_bars(code, period, advance_dates[0], advance_dates[-1])
                if b["trade_time"] in set(advance_dates)
            ]
        else:
            bars = []
    else:
        placeholders = ",".join("?" * len(advance_dates))
        bars = stock_query_all(
            f"SELECT trade_date, open, high, low, close FROM kline_daily "
            f"WHERE code = ? AND adjust_type = 'qfq' AND trade_date IN ({placeholders}) "
            f"ORDER BY trade_date ASC",
            (code, *advance_dates),
        )
    triggered = []
    triggered_today = set()
    for b in bars:
        # 日期部分: 分钟模式取 trade_time 前 10 位(自然日), 日线模式即 trade_date 本身
        b_date = b[0][:10]
        b_open, b_high, b_low, b_close = b[1], b[2], b[3], b[4]
        # 跳过今天已触发的
        if b_date in triggered_today:
            continue
        # 止损: bar.low <= avg_cost * (1 - stop_pct)
        if stop_pct > 0 and float(b_low) <= avg_cost * (1 - stop_pct):
            triggered.append({
                "type": "stop_loss",
                "code": code, "qty": qty,
                "price": round(avg_cost * (1 - stop_pct), 2),
                "pnl_pct": -stop_pct * 100,
                "date": b_date,
                "trigger_price": float(b_low),
                "avg_cost": avg_cost,
            })
            triggered_today.add(b_date)
            break  # 一次只触发一种
        # 止盈: bar.high >= avg_cost * (1 + take_pct)
        if take_pct > 0 and float(b_high) >= avg_cost * (1 + take_pct):
            triggered.append({
                "type": "take_profit",
                "code": code, "qty": qty,
                "price": round(avg_cost * (1 + take_pct), 2),
                "pnl_pct": take_pct * 100,
                "date": b_date,
                "trigger_price": float(b_high),
                "avg_cost": avg_cost,
            })
            triggered_today.add(b_date)
            break
    return triggered


def _auto_execute_risk_orders(sess: dict, user_id: int, triggered: list) -> list:
    """执行风控自动单(用市价 open 价成交)。返回写出的 order_id 列表。"""
    if not triggered:
        return []
    out = []
    with get_conn() as conn:
        for t in triggered:
            trade_date = t["date"]
            qty = t["qty"]
            # 用 open 价成交 (如果有触发价更接近的, 用 min/max)
            bar = stock_query_one(
                "SELECT open FROM kline_daily WHERE code = ? AND adjust_type = 'qfq' AND trade_date = ?",
                (sess["code"], trade_date),
            )
            exec_price = float(bar[0]) if bar and bar[0] else t["price"]
            # 重新计算 fees
            sess_for_fee = {
                "commission_rate": sess["commission_rate"],
                "min_commission": sess["min_commission"],
                "stamp_tax": sess["stamp_tax"],
                "transfer_fee": sess["transfer_fee"],
            }
            trade_amount = qty * exec_price
            fees = _calc_total_fees(trade_amount, qty, sess_for_fee, "SELL")
            cost_basis, fee_prop = _fifo_cost_basis(user_id, sess["id"], qty)
            realized_pnl = trade_amount - fees["total_fee"] - cost_basis - fee_prop
            cur = conn.execute(
                """INSERT INTO training_order(
                    session_id, user_id, trade_date, side, price, quantity, amount,
                    commission, stamp_tax, transfer_fee, total_fee, realized_pnl, pending_status, note
                ) VALUES(?, ?, ?, 'SELL', ?, ?, ?, ?, ?, ?, ?, ?, 'filled', ?)""",
                (sess["id"], user_id, trade_date,
                 exec_price, qty, trade_amount,
                 fees["commission"], fees["stamp_tax"], fees["transfer_fee"], fees["total_fee"],
                 round(realized_pnl, 2),
                 f"风控自动 {t['type']} 触发: {t['pnl_pct']:+.1f}% (触发价 ¥{t['trigger_price']:.2f})"),
            )
            order_id = cur.lastrowid
            # 更新持仓
            new_q = qty - qty
            if new_q <= 0:
                conn.execute(
                    "DELETE FROM training_position WHERE session_id = ? AND code = ?",
                    (sess["id"], sess["code"]),
                )
            else:
                conn.execute(
                    "UPDATE training_position SET quantity = ? WHERE session_id = ? AND code = ?",
                    (new_q, sess["id"], sess["code"]),
                )
            # 钱包加款
            net_recv = trade_amount - fees["total_fee"]
            conn.execute(
                "UPDATE training_wallet SET balance = balance + ? WHERE user_id = ?",
                (net_recv, user_id),
            )
            _record_event(
                conn, sess["id"], user_id, "sell", trade_date,
                payload={
                    "order_id": order_id, "code": sess["code"],
                    "qty": qty, "price": exec_price, "net_recv": net_recv,
                    "fees": fees, "is_risk_auto": True,
                    "risk_type": t["type"], "trigger_pct": t["pnl_pct"],
                },
                snapshot={"avg_cost": t["avg_cost"], "is_risk_auto": True},
            )
            out.append({
                "order_id": order_id,
                "type": t["type"],
                "qty": qty, "price": exec_price,
                "realized_pnl": round(realized_pnl, 2),
                "date": trade_date,
            })
    return out


def _process_pending_orders(sess: dict, advance_dates: list, user_id: int) -> dict:
    """处理 pending 限价单(2026-07-31 优化)。

    对每个 pending 订单:
      1) 在 advance 期间找到触及限价的 bar → 成交 (更新 status + 持仓 + 钱包)
      2) 在 advance 期间未触及 → 留 pending
      3) 创建时间距今 > 20 个交易日 → 标记 expired
    返回统计 {filled: int, expired: int, still_pending: int}。
    """
    pending_orders = query_all(
        "SELECT id, trade_date, side, price, quantity, amount, "
        "       commission, stamp_tax, transfer_fee, total_fee, note, "
        "       created_at "
        "FROM training_order "
        "WHERE session_id = ? AND user_id = ? AND pending_status = 'pending' "
        "ORDER BY id ASC",
        (sess["id"], user_id),
    )
    if not pending_orders:
        return {"filled": 0, "expired": 0, "still_pending": 0}

    # 解析 TTL
    stats = {"filled": 0, "expired": 0, "still_pending": 0}
    code = sess["code"]
    # 2026-08-04 分钟级: 分钟模式用 kline_minute(trade_time 为 key), 日线用 kline_daily
    period = _session_period(sess)
    is_minute = period in (30, 60)
    # 拉 advance 期间的所有 bar (含 high/low/open/close)
    # 分钟模式用 _minute_bars(真实数据优先, 无则日K合成);日线用 kline_daily。
    if advance_dates:
        if is_minute:
            bars = [
                (b["trade_time"], b["open"], b["high"], b["low"], b["close"])
                for b in _minute_bars(code, period, advance_dates[0], advance_dates[-1])
                if b["trade_time"] in set(advance_dates)
            ]
        else:
            placeholders = ",".join("?" * len(advance_dates))
            bars = stock_query_all(
                f"SELECT trade_date, open, high, low, close FROM kline_daily "
                f"WHERE code = ? AND adjust_type = 'qfq' "
                f"  AND trade_date IN ({placeholders}) "
                f"ORDER BY trade_date ASC",
                (code, *advance_dates),
            )
    else:
        bars = []
    bar_by_date = {b[0]: b for b in bars}

    with get_conn() as conn:
        for po in pending_orders:
            po_id, po_trade_date, po_side, po_price, po_qty, po_amount, \
                po_commission, po_stamp, po_transfer, po_total_fee, po_note, po_created = po
            # 找首个触及限价的 bar (BUY 限价 <= high && >= low; SELL 同理)
            filled = False
            for b_date in advance_dates:
                bar = bar_by_date.get(b_date)
                if not bar:
                    continue
                # 分钟模式 b_date 为完整 trade_time, T+1/订单 trade_date 用自然日部分
                d_key = b_date[:10] if is_minute else b_date
                _, b_open, b_high, b_low, b_close = bar
                # 触及条件: low <= price <= high
                if float(b_low) - 0.001 <= po_price <= float(b_high) + 0.001:
                    # 成交价: BUY 用 min(open, price), SELL 用 max(open, price)
                    exec_price = min(float(b_open), po_price) if po_side == "BUY" else max(float(b_open), po_price)
                    # 重新计算 fees
                    sess_for_fee = {
                        "commission_rate": sess["commission_rate"],
                        "min_commission": sess["min_commission"],
                        "stamp_tax": sess["stamp_tax"],
                        "transfer_fee": sess["transfer_fee"],
                    }
                    trade_amount = po_qty * exec_price
                    fees = _calc_total_fees(trade_amount, po_qty, sess_for_fee, po_side)
                    # 写订单状态更新
                    if po_side == "BUY":
                        new_total_pay = trade_amount + fees["total_fee"]
                        # 校验现金
                        cur = conn.execute(
                            "SELECT balance FROM training_wallet WHERE user_id = ?",
                            (user_id,),
                        ).fetchone()
                        cash_now = float(cur[0] or 0) if cur else 0
                        if cash_now < new_total_pay:
                            # 现金不足 → 标 expired
                            conn.execute(
                                "UPDATE training_order SET pending_status = 'expired', "
                                "note = ? WHERE id = ?",
                                (f"触及限价但现金不足,自动失效 (b_date={b_date})", po_id),
                            )
                            stats["expired"] += 1
                            continue
                        # 更新持仓
                        row = conn.execute(
                            "SELECT quantity, avg_cost FROM training_position "
                            "WHERE session_id = ? AND code = ?",
                            (sess["id"], code),
                        ).fetchone()
                        if row:
                            old_q, old_avg = row
                            old_cost = old_q * (old_avg or 0)
                            new_buy_cost = po_qty * exec_price + fees["total_fee"]
                            new_q = old_q + po_qty
                            new_avg = (old_cost + new_buy_cost) / new_q
                            conn.execute(
                                "UPDATE training_position SET quantity = ?, avg_cost = ? "
                                "WHERE session_id = ? AND code = ?",
                                (new_q, new_avg, sess["id"], code),
                            )
                        else:
                            full_cost = po_qty * exec_price + fees["total_fee"]
                            conn.execute(
                                "INSERT INTO training_position(session_id, user_id, code, quantity, avg_cost) "
                                "VALUES(?, ?, ?, ?, ?)",
                                (sess["id"], user_id, code, po_qty, full_cost / po_qty),
                            )
                        # 钱包扣款
                        conn.execute(
                            "UPDATE training_wallet SET balance = balance - ?, "
                            "total_spent = total_spent + ? WHERE user_id = ?",
                            (new_total_pay, new_total_pay, user_id),
                        )
                    else:  # SELL
                        # T+1 校验
                        today_buy = (conn.execute(
                            "SELECT COALESCE(SUM(quantity), 0) FROM training_order "
                            "WHERE session_id = ? AND user_id = ? AND side = 'BUY' AND trade_date = ?",
                            (sess["id"], user_id, d_key),
                        ).fetchone() or (0,))[0] or 0
                        today_sell = (conn.execute(
                            "SELECT COALESCE(SUM(quantity), 0) FROM training_order "
                            "WHERE session_id = ? AND user_id = ? AND side = 'SELL' AND trade_date = ?",
                            (sess["id"], user_id, d_key),
                        ).fetchone() or (0,))[0] or 0
                        t1_locked = max(0, int(today_buy) - int(today_sell))
                        row = conn.execute(
                            "SELECT quantity, avg_cost FROM training_position "
                            "WHERE session_id = ? AND code = ?",
                            (sess["id"], code),
                        ).fetchone()
                        sellable = int(row[0]) - t1_locked if row else 0
                        if sellable < po_qty:
                            conn.execute(
                                "UPDATE training_order SET pending_status = 'expired', "
                                "note = ? WHERE id = ?",
                                (f"触及限价但 T+1 限制/可卖不足,自动失效 (b_date={b_date})", po_id),
                            )
                            stats["expired"] += 1
                            continue
                        # 更新持仓
                        cost_basis, fee_prop = _fifo_cost_basis(user_id, sess["id"], po_qty)
                        realized_pnl = trade_amount - fees["total_fee"] - cost_basis - fee_prop
                        new_q = int(row[0]) - po_qty
                        if new_q <= 0:
                            conn.execute(
                                "DELETE FROM training_position WHERE session_id = ? AND code = ?",
                                (sess["id"], code),
                            )
                        else:
                            conn.execute(
                                "UPDATE training_position SET quantity = ? "
                                "WHERE session_id = ? AND code = ?",
                                (new_q, sess["id"], code),
                            )
                        net_recv = trade_amount - fees["total_fee"]
                        conn.execute(
                            "UPDATE training_wallet SET balance = balance + ? "
                            "WHERE user_id = ?",
                            (net_recv, user_id),
                        )
                    # 标记订单为 filled, 写入实际成交价 + 重新计算的 fees
                    conn.execute(
                        "UPDATE training_order SET pending_status = 'filled', "
                        "  trade_date = ?, trade_time = ?, price = ?, amount = ?, "
                        "  commission = ?, stamp_tax = ?, transfer_fee = ?, total_fee = ?, "
                        "  realized_pnl = COALESCE(realized_pnl, 0), "
                        "  note = ? "
                        "WHERE id = ?",
                        (d_key, b_date if is_minute else None, exec_price, trade_amount,
                         fees["commission"], fees["stamp_tax"], fees["transfer_fee"], fees["total_fee"],
                         realized_pnl if po_side == "SELL" else 0,
                         f"限价单于 {d_key} 触及 ¥{po_price:.2f} 成交 @ ¥{exec_price:.2f}",
                         po_id),
                    )
                    _record_event(
                        conn, sess["id"], user_id, "buy" if po_side == "BUY" else "sell",
                        d_key,
                        payload={"order_id": po_id, "is_pending_filled": True,
                                 "exec_price": exec_price, "qty": po_qty},
                    )
                    stats["filled"] += 1
                    filled = True
                    break
            # 没成交 → 检查是否过期
            if not filled:
                # 计算 created 到 now 的交易日数 (近似用 advance 期间的天数)
                if advance_dates:
                    # 创建时间是否已超过 pending 默认 ttl (20 日)
                    try:
                        from datetime import datetime as _dt
                        created_dt = _dt.fromisoformat(po_created[:19] if po_created else "1970-01-01")
                        last_key = advance_dates[-1][:10] if is_minute else advance_dates[-1]
                        last_advance = _dt.strptime(last_key, "%Y-%m-%d")
                        days_passed = (last_advance - created_dt).days
                        if days_passed > 20:
                            conn.execute(
                                "UPDATE training_order SET pending_status = 'expired', "
                                "note = ? WHERE id = ?",
                                (f"超过 20 个交易日未触及,自动失效 (已过 {days_passed} 日)", po_id),
                            )
                            stats["expired"] += 1
                        else:
                            stats["still_pending"] += 1
                    except Exception:
                        stats["still_pending"] += 1
                else:
                    stats["still_pending"] += 1
    return stats


# =========================================================
# API
# =========================================================
@router.get("/sessions")
def list_my_sessions(user: dict = Depends(get_current_train_user)):
    """我的训练会话列表(草稿/dashboard 用)"""
    rows = query_all(
        "SELECT id, code, name, start_date, end_date, reveal_date, status, "
        "       initial_cash, created_at "
        "FROM training_session WHERE user_id = ? ORDER BY id DESC LIMIT 30",
        (user["id"],),
    )
    return {
        "items": [{
            "id": r[0], "code": r[1], "name": r[2],
            "start_date": r[3], "end_date": r[4], "current_date": r[5],
            "status": r[6], "initial_cash": r[7], "created_at": r[8],
        } for r in rows]
    }


@router.get("/industries")
def list_train_industries():
    """训练端可用的行业列表(无需 admin token)。

    2026-08-04 P0-3 修复:
    - 旧版 Setup.vue 直接调 `/api/stocks/industries`, 该接口强制 require_admin,
      训练用户无 admin token → 401;
    - 前端 axios 拦截器把"在 /train/* 页面的非 /train/ URL 401"误判为
      train auth 失败 → 清空 train state → 用户被踢回登录页
      ("用户端登录已过期")。
    - 现在训练端自带 industries 端点, 走 train cookie 即可拿到行业列表,
      不再触发误判。

    复用 stock_list 行业统计 (与 /api/stocks/industries 一致), 行为等价。
    """
    rows = stock_query_all(
        "SELECT industry, COUNT(*) FROM stock_list "
        "WHERE is_active = 1 AND industry IS NOT NULL AND industry != '' "
        "GROUP BY industry ORDER BY 2 DESC"
    )
    return {"items": [{"industry": r[0], "count": r[1]} for r in rows]}


@router.post("/sessions/start")
@limiter.limit("20/minute")
def start_session(req: TrainingSetupRequest, request: Request, response: Response, user: dict = Depends(get_current_train_user)):
    """发起一场训练:不再扣任何训练费(2026-07-31 取消),随机选股、写入 session"""
    # 训练费已取消,统一从 app/utils.calc_session_cost 取(恒为 0)
    session_cost = calc_session_cost(req.start_date, req.end_date, req.initial_cash)

    # 2026-08-04 分钟级: 组合训练暂不接分钟K线(组合+分钟状态机过于复杂),
    # 直接拒绝, 组合继续走日线老路径。
    if req.is_portfolio and req.bar_period in (30, 60):
        raise HTTPException(status_code=400, detail="组合训练暂不支持分钟K线")

    # 2026-07-31 优化: 组合训练模式 (P2-2)
    if req.is_portfolio:
        return _start_portfolio_sessions(req, user, session_cost)

    # 2026-08-04 P0-3 修复: 防御性兜底,即使 get_user_conn 的"吞异常"行为被
    # 彻底修好 (现在已 raise), 也要保证 sid 未定义时给出友好 5xx 而不是
    # UnboundLocalError。这是"双保险", 单点修复 get_user_conn 也可消除
    # 这个 UnboundLocalError, 但保留防御让外部 INSERT 失败时仍能定位。
    sid: Optional[int] = None
    balance_after: float = 0.0

    try:
        with get_conn() as conn:
            # 读取当前钱包余额(不扣训练费,仅检查余额是否充足)
            row = conn.execute(
                "SELECT balance FROM training_wallet WHERE user_id = ?",
                (user["id"],),
            ).fetchone()
            if row is None:
                # 钱包不存在则初始化
                conn.execute(
                    "INSERT INTO training_wallet(user_id, balance) VALUES(?, 0)",
                    (user["id"],),
                )
                balance_after = 0.0
            else:
                balance_after = float(row[0] or 0)

            # 训练可用资金上限 = 钱包余额(2026-07-31 起不再扣训练费,也不再保留余量)
            max_initial = max(0.0, balance_after)
            if req.initial_cash is None or req.initial_cash <= 0:
                # 未提供则默认 = max_initial
                session_initial_cash = max_initial
            else:
                if req.initial_cash > max_initial:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"初始资金 ¥ {req.initial_cash:.2f} 超过钱包余额 ¥ {max_initial:.2f}"
                        ),
                    )
                session_initial_cash = float(req.initial_cash)

            # 初始资金下限 1000 元(跟前端 Setup.vue 校验一致)
            if session_initial_cash < 1000:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"初始资金需 ≥ ¥1000,当前钱包余额 ¥{max_initial:.2f} (请先兑换充值)"
                    ),
                )

            # 随机选股(使用后端确定的 initial_cash 覆盖入参,保持 _pick_random_stock 一致)
            req_dict = req.model_dump()
            req_dict["initial_cash"] = session_initial_cash
            req_sub = TrainingSetupRequest(**req_dict)
            stock = _pick_random_stock(req_sub)

            # 2026-08-04 分钟级: 会话 K 线周期
            period = int(req.bar_period or 240)
            is_minute = period in (30, 60)

            # 初始揭示 = 训练开始日,但若 start_date 是节假日/周末没有 K 线,
            # 自动顺延到该股票的下个实际交易日,否则前端会拿到空 K 线图
            # 注意:用户会话在 user_tx 内,但 kline_daily/kline_minute 在 stock.db,必须单独查
            if is_minute:
                # 分钟模式(2026-08-12): 分钟K由日K合成, 覆盖校验改为日线;
                # 首根 bar(trade_time) >= start_date 作为初始揭示。
                dcov = stock_query_one(
                    "SELECT COUNT(*) FROM kline_daily "
                    "WHERE code = ? AND adjust_type = 'qfq' "
                    "  AND trade_date >= ? AND trade_date <= ?",
                    (stock["code"], req.start_date, req.end_date),
                )
                if not dcov or (dcov[0] or 0) == 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"该股票在所选区间无日K线数据,无法合成 {period}分钟K线,请调整训练日期",
                    )
                mbar = _minute_bars(stock["code"], period, f"{req.start_date} 00:00:00", f"{req.end_date} 23:59:59")
                current_dt = mbar[0]["trade_time"] if mbar else req.start_date
                reveal_date_val = current_dt[:10]
                reveal_time_val = current_dt
            else:
                kline_row = stock_query_one(
                    "SELECT MIN(trade_date) FROM kline_daily "
                    "WHERE code = ? AND adjust_type = 'qfq' AND trade_date >= ?",
                    (stock["code"], req.start_date),
                )
                current_dt = (kline_row[0] if kline_row and kline_row[0] else req.start_date)
                reveal_date_val = current_dt
                reveal_time_val = None

            cur = conn.execute(
                """INSERT INTO training_session(
                    user_id, code, name, industry, market,
                    start_date, end_date, lookback_months, initial_cash,
                    commission_rate, min_commission, stamp_tax, transfer_fee,
                    allow_split, max_positions, per_trade_amount,
                    allow_chinext, allow_st, allow_kcb, allow_bj,
                    total_fee_paid, status, reveal_date, bar_period, reveal_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
                (user["id"], stock["code"], stock["name"], stock["industry"], stock["market"],
                 req.start_date, req.end_date, req.lookback_months, session_initial_cash,
                 req.commission_rate, req.min_commission, req.stamp_tax, req.transfer_fee,
                 int(req.allow_split), req.max_positions, req.per_trade_amount,
                 int(req.allow_chinext), int(req.allow_st), int(req.allow_kcb), int(req.allow_bj),
                 session_cost, reveal_date_val, period, reveal_time_val),
            )
            sid_raw = cur.lastrowid
            if not sid_raw:
                # 不太可能发生(只有极少数 PG/SQLite 边界场景),但防御一下
                raise HTTPException(
                    status_code=500,
                    detail="创建训练会话失败: 数据库未返回新会话 ID",
                )
            sid = int(sid_raw)
            # 初始权益 = 本场训练的初始资金(钱包不再被扣训练费)
            conn.execute(
                "INSERT INTO training_equity(session_id, trade_date, trade_time, cash, market_value, total_equity) "
                "VALUES(?, ?, ?, ?, 0, ?)",
                (sid, reveal_date_val, reveal_time_val, session_initial_cash, session_initial_cash),
            )

        # 重新读取
        row = query_one("SELECT * FROM training_session WHERE id = ?", (sid,))
        session = dict(zip(SESSION_COLS, row))
        view = _build_session_view(session)
        view["session_cost"] = session_cost
        view["wallet_balance_after"] = balance_after
        return view
    except HTTPException:
        # FastAPI 业务 4xx: 原样上抛
        raise
    except Exception as e:
        # 2026-08-04 P0-3: 不再让 UnboundLocalError 之类的内部错误裸出,
        # 至少在 5xx 响应里给出可读 message + 让 error_id 能在日志里 grep。
        log.exception(
            "[start_session] 创建训练会话失败 user_id=%s code=%s err=%s",
            user.get("id"), getattr(req, "__dict__", {}).get("start_date"), e,
        )
        raise HTTPException(
            status_code=500,
            detail=f"创建训练会话失败,请稍后重试 ({type(e).__name__})",
        )


def _start_portfolio_sessions(req: TrainingSetupRequest, user: dict, session_cost: float) -> dict:
    """2026-07-31 优化 (P2-2): 组合训练 - 同时建 N 个 session 共享钱包。
    资金按 portfolio_size 均分到每只股;每只股独立 session 但用 reveal_date 字段记录 parent_id。
    """
    size = max(2, req.portfolio_size or 5)
    per_cash = float(req.initial_cash or 0) / size
    if per_cash < 1000:
        raise HTTPException(
            status_code=400,
            detail=f"组合训练每只股至少 ¥1000,需要 initial_cash >= ¥{1000 * size}",
        )

    with get_conn() as conn:
        # 余额校验
        row = conn.execute(
            "SELECT balance FROM training_wallet WHERE user_id = ?",
            (user["id"],),
        ).fetchone()
        balance = float(row[0] or 0) if row else 0.0
        if balance < float(req.initial_cash or 0):
            raise HTTPException(
                status_code=402,
                detail=f"钱包余额不足,需要 ¥{req.initial_cash:.2f},当前 ¥{balance:.2f}",
            )

        created = []
        used_codes = set()
        for i in range(size):
            # 尝试选不重复的股
            chosen = None
            for _ in range(10):
                cand = _pick_random_stock(req)
                if cand["code"] not in used_codes:
                    chosen = cand
                    break
            if not chosen:
                chosen = _pick_random_stock(req)
            used_codes.add(chosen["code"])

            cur = conn.execute(
                """INSERT INTO training_session(
                    user_id, code, name, industry, market,
                    start_date, end_date, lookback_months, initial_cash,
                    commission_rate, min_commission, stamp_tax, transfer_fee,
                    allow_split, max_positions, per_trade_amount,
                    allow_chinext, allow_st, allow_kcb, allow_bj,
                    total_fee_paid, status, reveal_date, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
                (user["id"], chosen["code"], chosen["name"], chosen["industry"], chosen["market"],
                 req.start_date, req.end_date, req.lookback_months, per_cash,
                 req.commission_rate, req.min_commission, req.stamp_tax, req.transfer_fee,
                 int(req.allow_split), 1, per_cash,  # max_positions=1 限制单只
                 int(req.allow_chinext), int(req.allow_st), int(req.allow_kcb), int(req.allow_bj),
                 session_cost, req.start_date,
                 f"portfolio:{i+1}/{size}:{chosen['code']}"),
            )
            sid = cur.lastrowid
            conn.execute(
                "INSERT INTO training_equity(session_id, trade_date, cash, market_value, total_equity) "
                "VALUES(?, ?, ?, 0, ?)",
                (sid, req.start_date, per_cash, per_cash),
            )
            created.append({
                "id": sid, "code": chosen["code"], "name": chosen["name"],
                "initial_cash": per_cash,
            })
        parent_id = created[0]["id"] if created else None

    return {
        "is_portfolio": True,
        "portfolio_id": parent_id,
        "size": size,
        "initial_cash": float(req.initial_cash),
        "per_session_cash": per_cash,
        "sessions": created,
        "message": f"成功创建 {len(created)} 个组合训练 session",
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: int, user: dict = Depends(get_current_train_user)):
    row = query_one("SELECT * FROM training_session WHERE id = ? AND user_id = ?",
                    (session_id, user["id"]))
    if not row:
        raise HTTPException(status_code=404, detail="训练会话不存在")
    session = dict(zip(SESSION_COLS, row))
    return _build_session_view(session)


@router.get("/sessions/{session_id}/signals")
def get_signals(session_id: int, user: dict = Depends(get_current_train_user)):
    """当前 bar 的技术指标 + 信号 (2026-07-31 优化)。

    返回:
      - indicators: MA5/MA10/MA20/MA60、RSI、MACD、量比
      - signals: [{type, level, desc}, ...] 信号列表
    """
    sess = _session_for_user(user["id"], session_id)
    code = sess["code"]
    reveal = sess["reveal_date"] or sess["start_date"]
    # 拉所有 bar (从 lookback_start 到 reveal) - 跟前端一致
    try:
        from datetime import datetime as _dt
        sd = _dt.strptime(sess["start_date"], "%Y-%m-%d").date()
        lookback = sess["lookback_months"] or 6
        y = sd.year - (lookback // 12)
        m = sd.month - (lookback % 12)
        while m <= 0:
            m += 12; y -= 1
        lookback_start = f"{y:04d}-{m:02d}-{sd.day:02d}"
    except Exception:
        lookback_start = sess["start_date"]
    bars = stock_query_all(
        "SELECT trade_date, open, high, low, close, volume FROM kline_daily "
        "WHERE code = ? AND adjust_type = 'qfq' AND trade_date >= ? AND trade_date <= ? "
        "ORDER BY trade_date ASC",
        (code, lookback_start, reveal),
    )
    if not bars:
        return {"indicators": {}, "signals": []}

    closes = [float(b[4]) for b in bars]
    volumes = [float(b[5] or 0) for b in bars]

    def sma(arr, n):
        if len(arr) < n: return None
        return sum(arr[-n:]) / n

    def rsi(arr, n=14):
        if len(arr) < n + 1: return None
        gains, losses = 0.0, 0.0
        for i in range(-n, 0):
            d = arr[i] - arr[i - 1]
            if d > 0: gains += d
            else: losses -= d
        if losses == 0: return 100.0
        rs = (gains / n) / (losses / n)
        return round(100 - 100 / (1 + rs), 2)

    def macd(arr, fast=12, slow=26, signal=9):
        if len(arr) < slow + signal: return None, None, None
        def ema(series, n):
            k = 2 / (n + 1)
            e = series[0]
            for v in series[1:]:
                e = v * k + e * (1 - k)
            return e
        ema_fast = ema(arr[-slow - fast + 1:], fast)
        ema_slow = ema(arr, slow)
        if ema_fast is None or ema_slow is None: return None, None, None
        diff = ema_fast - ema_slow
        # DEA 简化为差值的 9 期均值
        if len(arr) >= slow + signal:
            diffs = []
            k = 2 / (signal + 1)
            for i in range(slow, len(arr)):
                # 简化: 用整段差值近似的 ema, 不严格
                diffs.append(closes[i] - closes[i - 1])
            dea = sum(diffs[-signal:]) / signal if diffs else 0
        else:
            dea = 0
        return round(diff, 4), round(dea, 4), round((diff - dea) * 2, 4)  # 柱 = 2*(DIF-DEA)

    ma5, ma10, ma20, ma60 = sma(closes, 5), sma(closes, 10), sma(closes, 20), sma(closes, 60)
    rsi14 = rsi(closes, 14)
    dif, dea, macd_bar = macd(closes)
    # 量比: 最近一日量 / 5 日均量
    vol_ratio = None
    if len(volumes) >= 6:
        avg5 = sum(volumes[-6:-1]) / 5
        if avg5 > 0:
            vol_ratio = round(volumes[-1] / avg5, 2)

    # 信号生成
    signals = []
    if ma5 is not None and ma10 is not None and ma20 is not None:
        # 金叉/死叉 (MA5 vs MA10)
        prev_ma5 = sma(closes[:-1], 5)
        prev_ma10 = sma(closes[:-1], 10)
        if prev_ma5 and prev_ma10:
            if prev_ma5 <= prev_ma10 and ma5 > ma10:
                signals.append({"type": "MA金叉", "level": "bullish",
                                 "desc": f"MA5({ma5:.2f}) 上穿 MA10({ma10:.2f}), 短期看多信号"})
            elif prev_ma5 >= prev_ma10 and ma5 < ma10:
                signals.append({"type": "MA死叉", "level": "bearish",
                                 "desc": f"MA5({ma5:.2f}) 下穿 MA10({ma10:.2f}), 短期看空信号"})
        # 价格站上 MA20
        cur_close = closes[-1]
        if cur_close > ma20 and (len(closes) < 2 or closes[-2] <= ma20):
            signals.append({"type": "突破MA20", "level": "bullish",
                             "desc": f"收盘 ¥{cur_close:.2f} 站上 MA20({ma20:.2f})"})
        elif cur_close < ma20 and (len(closes) < 2 or closes[-2] >= ma20):
            signals.append({"type": "跌破MA20", "level": "bearish",
                             "desc": f"收盘 ¥{cur_close:.2f} 跌破 MA20({ma20:.2f})"})
    if rsi14 is not None:
        if rsi14 >= 70:
            signals.append({"type": "RSI超买", "level": "warn",
                             "desc": f"RSI = {rsi14}, 警惕回调风险"})
        elif rsi14 <= 30:
            signals.append({"type": "RSI超卖", "level": "bullish",
                             "desc": f"RSI = {rsi14}, 可能反弹"})
    if vol_ratio is not None and vol_ratio >= 2.0:
        signals.append({"type": "放量", "level": "info",
                         "desc": f"量比 {vol_ratio}×, 显著高于 5 日均量"})

    return {
        "indicators": {
            "ma5": round(ma5, 2) if ma5 else None,
            "ma10": round(ma10, 2) if ma10 else None,
            "ma20": round(ma20, 2) if ma20 else None,
            "ma60": round(ma60, 2) if ma60 else None,
            "rsi14": rsi14,
            "macd_dif": dif, "macd_dea": dea, "macd_bar": macd_bar,
            "vol_ratio": vol_ratio,
        },
        "signals": signals,
        "trade_date": reveal,
    }


@router.get("/sessions/{session_id}/attribution")
def get_attribution(session_id: int, user: dict = Depends(get_current_train_user)):
    """盈亏归因分析(2026-07-31 优化): 拆解实际盈亏 = 市场贡献 + 选股超额 + 时机贡献。

    假设:
      - market = 同期沪深 300 (sh000300) 涨幅 × 初始资金
      - selection = 个股涨幅 - 沪深 300 涨幅 (在用户买入价 和 卖出价之间)
      - timing = 实际盈亏 - market - selection
    """
    sess = _session_for_user(user["id"], session_id)
    initial_cash = float(sess["initial_cash"] or 0)
    if initial_cash <= 0:
        return {"error": "无效初始资金"}

    # 拉训练场的所有 BUY + SELL 订单 (用 round_trip 思路)
    orders = query_all(
        "SELECT trade_date, side, price, quantity, realized_pnl "
        "FROM training_order WHERE session_id = ? AND user_id = ? "
        "AND pending_status IN ('filled', '') OR pending_status IS NULL "
        "ORDER BY trade_date ASC, id ASC",
        (session_id, user["id"]),
    )
    # 计算已实现盈亏
    realized = sum(float(o[4] or 0) for o in orders if o[1] == "SELL")
    # 当前持仓市值 (如果还有持仓)
    last_close_row = stock_query_one(
        "SELECT close FROM kline_daily WHERE code = ? AND adjust_type = 'qfq' "
        "AND trade_date <= ? ORDER BY trade_date DESC LIMIT 1",
        (sess["code"], sess["reveal_date"] or sess["start_date"]),
    )
    last_close = float(last_close_row[0] or 0) if last_close_row else 0
    pos_row = query_one(
        "SELECT quantity, avg_cost FROM training_position WHERE session_id = ? AND code = ?",
        (session_id, sess["code"]),
    )
    holding_value = 0
    if pos_row and pos_row[0] > 0:
        # 浮动盈亏 = qty * (last_close - avg_cost)
        holding_value = float(pos_row[0]) * (last_close - float(pos_row[1] or 0))
    total_pnl = realized + holding_value
    pnl_pct = total_pnl / initial_cash * 100

    # 训练期: start_date ~ reveal_date (用 end_date 不太合理, 用户可能没推完)
    start_d = sess["start_date"]
    end_d = sess["reveal_date"] or sess["end_date"]

    # 拉训练期 沪深 300 涨幅
    hs_row = stock_query_one(
        "SELECT close FROM index_daily WHERE code = 'sh000300' AND trade_date = ?",
        (start_d,),
    )
    hs_end_row = stock_query_one(
        "SELECT close FROM index_daily WHERE code = 'sh000300' AND trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT 1",
        (end_d,),
    )
    if not hs_row or not hs_row[0] or not hs_end_row or not hs_end_row[0]:
        return {"error": "无法获取沪深 300 同期数据 (index_daily 可能缺失)"}
    hs_start = float(hs_row[0])
    hs_end = float(hs_end_row[0])
    hs_return = (hs_end - hs_start) / hs_start * 100

    # 训练场个股涨幅 (从首根 bar 到末根)
    code_start = stock_query_one(
        "SELECT close FROM kline_daily WHERE code = ? AND adjust_type = 'qfq' AND trade_date = ?",
        (sess["code"], start_d),
    )
    code_end = stock_query_one(
        "SELECT close FROM kline_daily WHERE code = ? AND adjust_type = 'qfq' AND trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT 1",
        (sess["code"], end_d),
    )
    code_return = 0
    if code_start and code_start[0] and code_end and code_end[0]:
        code_return = (float(code_end[0]) - float(code_start[0])) / float(code_start[0]) * 100

    # 拆解
    market_contrib = hs_return
    selection_contrib = code_return - hs_return
    timing_contrib = pnl_pct - market_contrib - selection_contrib

    # 文字解读
    analysis = []
    if abs(market_contrib) > 0.5:
        if market_contrib > 0:
            analysis.append(f"📈 市场环境向好:沪深 300 同期 {market_contrib:+.2f}%,给你贡献了 ¥{initial_cash * market_contrib / 100:,.0f}")
        else:
            analysis.append(f"📉 市场环境恶劣:沪深 300 同期 {market_contrib:+.2f}%,拖累了 ¥{initial_cash * abs(market_contrib) / 100:,.0f}")
    if abs(selection_contrib) > 0.5:
        if selection_contrib > 0:
            analysis.append(f"⭐ 选股能力:跑赢市场 {selection_contrib:+.2f}%,这只股本身不错")
        else:
            analysis.append(f"⚠️ 选股欠佳:跑输市场 {selection_contrib:+.2f}%,考虑换更强势的标的")
    if abs(timing_contrib) > 0.5:
        if timing_contrib > 0:
            analysis.append(f"🎯 择时优秀:在 {timing_contrib:+.2f}% 之上额外获利 ¥{initial_cash * timing_contrib / 100:,.0f}")
        else:
            analysis.append(f"⏰ 择时欠佳:少赚了 ¥{initial_cash * abs(timing_contrib) / 100:,.0f} (买卖时机可优化)")

    return {
        "session_id": session_id,
        "initial_cash": initial_cash,
        "total_pnl": round(total_pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "period": {"start": start_d, "end": end_d},
        "attribution": {
            "market_pct": round(market_contrib, 2),
            "selection_pct": round(selection_contrib, 2),
            "timing_pct": round(timing_contrib, 2),
            "stock_return_pct": round(code_return, 2),
            "benchmark_return_pct": round(hs_return, 2),
        },
        "amounts": {
            "market_yuan": round(initial_cash * market_contrib / 100, 2),
            "selection_yuan": round(initial_cash * selection_contrib / 100, 2),
            "timing_yuan": round(initial_cash * timing_contrib / 100, 2),
        },
        "analysis": analysis,
    }


@router.get("/sessions/{session_id}/benchmark")
def get_benchmark_signals(session_id: int, user: dict = Depends(get_current_train_user)):
    """复盘"该买/该卖"信号 (2026-07-31 优化) - 用 SMA 金叉死叉策略回放整个训练区间。

    返回:
      - signals: [{date, type: "buy"/"sell", price}, ...] 策略信号
      - user_trades: [{date, side, price}, ...] 用户实际交易
      - alignment: {aligned: int, misaligned: int, missed: int} 一致性统计
    """
    sess = _session_for_user(user["id"], session_id)
    code = sess["code"]
    # 拉所有 bar
    bars = stock_query_all(
        "SELECT trade_date, close FROM kline_daily "
        "WHERE code = ? AND adjust_type = 'qfq' AND trade_date >= ? AND trade_date <= ? "
        "ORDER BY trade_date ASC",
        (code, sess["start_date"], sess["end_date"]),
    )
    if not bars or len(bars) < 25:
        return {"signals": [], "user_trades": [], "alignment": {"aligned": 0, "misaligned": 0, "missed": 0}}

    # 算 MA5 / MA20
    closes = [(b[0], float(b[1])) for b in bars]
    def ma_n(idx, n=5):
        if idx < n - 1: return None
        return sum(c for _, c in closes[idx - n + 1:idx + 1]) / n

    # 生成信号: MA5 上穿 MA20 → BUY, 下穿 → SELL
    signals = []
    in_position = False
    for i in range(len(closes)):
        ma5 = ma_n(i, 5)
        ma20 = ma_n(i, 20)
        ma5_prev = ma_n(i - 1, 5) if i > 0 else None
        ma20_prev = ma_n(i - 1, 20) if i > 0 else None
        if not (ma5 and ma20 and ma5_prev and ma20_prev):
            continue
        # 金叉
        if ma5_prev <= ma20_prev and ma5 > ma20 and not in_position:
            signals.append({"date": closes[i][0], "type": "BUY", "price": closes[i][1]})
            in_position = True
        # 死叉
        elif ma5_prev >= ma20_prev and ma5 < ma20 and in_position:
            signals.append({"date": closes[i][0], "type": "SELL", "price": closes[i][1]})
            in_position = False

    # 用户实际操作
    user_orders = query_all(
        "SELECT trade_date, side, price FROM training_order "
        "WHERE session_id = ? AND user_id = ? "
        "AND (pending_status = 'filled' OR pending_status IS NULL OR pending_status = '') "
        "ORDER BY trade_date ASC, id ASC",
        (session_id, user["id"]),
    )
    user_trades = [
        {"date": o[0], "side": o[1], "price": float(o[2])}
        for o in user_orders
    ]

    # 一致性分析: 用户的 BUY/SELL 是否与策略信号"同日"匹配
    # 简化: 每个用户交易, 找最近 5 个交易日内同向的策略信号
    sig_dates = {s["date"]: s for s in signals}
    aligned = 0
    misaligned = 0
    missed = 0
    for t in user_trades:
        # 在 ±5 个交易日找同向信号
        from datetime import datetime as _dt, timedelta as _td
        try:
            td = _dt.strptime(t["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        found_match = False
        for offset in range(-5, 6):
            d = (td + _td(days=offset)).isoformat()
            if d in sig_dates and sig_dates[d]["type"] == t["side"]:
                aligned += 1
                found_match = True
                break
        if not found_match:
            # 反向 / 无信号
            for offset in range(-5, 6):
                d = (td + _td(days=offset)).isoformat()
                if d in sig_dates and sig_dates[d]["type"] != t["side"]:
                    misaligned += 1
                    found_match = True
                    break
            if not found_match:
                missed += 1

    return {
        "signals": signals,
        "user_trades": user_trades,
        "alignment": {
            "aligned": aligned,       # 与策略信号一致
            "misaligned": misaligned, # 与策略信号反向
            "missed": missed,         # 策略无信号时用户自决
        },
        "total_strategy_trades": len(signals),
        "total_user_trades": len(user_trades),
    }


@router.post("/sessions/{session_id}/advance")
@limiter.limit("60/minute")
def advance(session_id: int, req: AdvanceRequest, request: Request, response: Response, user: dict = Depends(get_current_train_user)):
    """时间推进:把 current_date 向后推 N 个交易日;返回新的视图"""
    sess = _session_for_user(user["id"], session_id)
    if sess["status"] != "active":
        raise HTTPException(status_code=400, detail="该训练已结束")

    # 2026-08-04 分钟级: 分钟模式按根推进, 日线模式按交易日推进
    period = _session_period(sess)
    is_minute = period in (30, 60)
    if is_minute:
        # 推进 bar 数: req.bars 优先, 否则按 days 换算 (旧前端只传 days)
        n_bars = req.bars if req.bars is not None else req.days * (16 if period == 30 else 8)
        cur_reveal = sess.get("reveal_time") or sess["reveal_date"] or sess["start_date"]
        mrows = _minute_bars(
            sess["code"], period,
            cur_reveal, f"{sess['end_date']} 23:59:59",
            limit=n_bars,
        )
        # 排除 == cur_reveal 本身(推进要求 > cur_reveal)
        mrows = [b for b in mrows if b["trade_time"] > cur_reveal]
        if not mrows:
            raise HTTPException(status_code=400, detail="已到达训练终点")
        new_current = mrows[-1]["trade_time"]
        advance_dates = [b["trade_time"] for b in mrows]
        execute(
            "UPDATE training_session SET reveal_time = ?, reveal_date = ?, "
            "updated_at = datetime('now','localtime') WHERE id = ?",
            (new_current, new_current[:10], sess["id"]),
        )
    else:
        # 找接下来 N 个交易日 (<= end_date)
        rows = stock_query_all(
            "SELECT trade_date FROM kline_daily "
            "WHERE code = ? AND adjust_type = 'qfq' AND trade_date > ? AND trade_date <= ? "
            "ORDER BY trade_date ASC LIMIT ?",
            (sess["code"], sess["reveal_date"], sess["end_date"], req.days),
        )
        if not rows:
            raise HTTPException(status_code=400, detail="已到达训练终点")
        new_current = rows[-1][0]
        advance_dates = [r[0] for r in rows]

        execute(
            "UPDATE training_session SET reveal_date = ?, updated_at = datetime('now','localtime') "
            "WHERE id = ?",
            (new_current, sess["id"]),
        )

    # 2026-07-31 优化: 处理 pending 限价单
    # 1) 触及限价 → 立即成交 (更新 order 状态 + 持仓 + 钱包)
    # 2) 未触及 → 留 pending
    # 3) 超过 pending_ttl (按 trade_date 间隔) → 标记 expired
    _process_pending_orders(sess, advance_dates, user["id"])

    # 2026-07-31 优化: 自动风控 (止损/止盈) 触发
    risk_triggered = _check_risk_rules(sess, advance_dates, user["id"], period)
    if risk_triggered:
        _auto_execute_risk_orders(sess, user["id"], risk_triggered)

    # 现金 = 当前钱包余额(共用资金)
    cash = _wallet_balance(user["id"])

    # 一次拉所有持仓代码的 close 列(逐 bar/日 close),用于插每个揭示 bar 的权益快照
    pos_codes = query_all(
        "SELECT code FROM training_position WHERE session_id = ? AND quantity > 0",
        (sess["id"],),
    )
    if pos_codes:
        code_list = [c[0] for c in pos_codes]
        close_map = {}   # code -> { key(trade_time or trade_date) -> close }
        if is_minute:
            want = set(advance_dates)
            for c in code_list:
                for b in _minute_bars(c, period, advance_dates[0], advance_dates[-1]):
                    if b["trade_time"] in want:
                        close_map.setdefault(c, {})[b["trade_time"]] = b["close"]
        else:
            for r in stock_query_all(
                f"SELECT code, trade_date, close FROM kline_daily "
                f"WHERE code IN ({','.join('?'*len(code_list))}) AND adjust_type = 'qfq' "
                f"  AND trade_date IN ({','.join('?'*len(advance_dates))})",
                tuple(code_list) + tuple(advance_dates),
            ):
                close_map.setdefault(r[0], {})[r[1]] = r[2]
    else:
        close_map = {}

    with get_conn() as conn:
        # 每个揭示 bar 插 1 条 equity 快照,曲线连续
        for d in advance_dates:
            mv = 0.0
            for c in close_map:
                # 持仓仅显示在 start_date 之后开仓的部分;这里用当前持仓量*该 bar close
                pos = query_one(
                    "SELECT quantity, avg_cost FROM training_position "
                    "WHERE session_id = ? AND code = ?",
                    (sess["id"], c),
                )
                if not pos or pos[0] <= 0:
                    continue
                qty, avg_cost = pos
                px = close_map[c].get(d, avg_cost or 0)
                mv += qty * px
            if is_minute:
                conn.execute(
                    "INSERT INTO training_equity(session_id, trade_date, trade_time, cash, market_value, total_equity) "
                    "VALUES(?, ?, ?, ?, ?, ?)",
                    (sess["id"], d[:10], d, cash, mv, cash + mv),
                )
            else:
                conn.execute(
                    "INSERT INTO training_equity(session_id, trade_date, cash, market_value, total_equity) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (sess["id"], d, cash, mv, cash + mv),
                )
        # 2026-07-31 P1-12: 记录 advance 事件 (分钟模式记 bars + reveal_time)
        if is_minute:
            _record_event(
                conn, sess["id"], user["id"], "advance", new_current[:10],
                payload={
                    "bars": len(advance_dates),
                    "days": req.days,
                    "advance_dates": advance_dates,
                    "new_reveal_time": new_current,
                    "new_reveal_date": new_current[:10],
                },
                snapshot={
                    "prev_reveal_date": sess["reveal_date"],
                    "prev_reveal_time": sess.get("reveal_time"),
                },
            )
        else:
            _record_event(
                conn, sess["id"], user["id"], "advance", new_current,
                payload={
                    "days": req.days,
                    "advance_dates": advance_dates,
                    "new_reveal_date": new_current,
                },
                snapshot={"prev_reveal_date": sess["reveal_date"]},
            )

    return get_session(session_id, user=user)


@router.get("/sessions/{session_id}/kline")
def session_kline(session_id: int, period: str = Query("daily", pattern="^(daily|weekly|monthly|30|60)$"),
                  user: dict = Depends(get_current_train_user)):
    """返回已揭示的日/周/月/30分/60分 K 线(含 lookback_months 历史回看)"""
    sess = _session_for_user(user["id"], session_id)
    reveal_date = sess["reveal_date"] or sess["start_date"]
    # 与 _build_session_view 保持一致:从 start_date - lookback_months 起
    from datetime import datetime as _dt
    try:
        sd = _dt.strptime(sess["start_date"], "%Y-%m-%d").date()
        lookback = sess["lookback_months"] or 6
        year = sd.year - (lookback // 12)
        month = sd.month - (lookback % 12)
        while month <= 0:
            month += 12
            year -= 1
        lookback_start = f"{year:04d}-{month:02d}-{sd.day:02d}"
    except Exception:
        lookback_start = sess["start_date"]
    # 2026-08-04 分钟级: period=30/60 直接查 kline_minute, 揭示终点用 reveal_time
    if period in ("30", "60"):
        reveal_end = sess.get("reveal_time") or reveal_date
        minute_items = _kline_in_window(sess["code"], lookback_start, reveal_end, int(period))
        return {"period": period, "items": minute_items}
    daily = _kline_in_window(sess["code"], lookback_start, reveal_date)
    # 如果 reveal_date 落在非交易日(节假日),顺延到下一个交易日,以保证至少返回当前 bar
    if daily and daily[-1]["trade_date"] < reveal_date:
        # 找 reveal_date 当天及之后的第一根 K 线
        next_bar = _kline_in_window(sess["code"], reveal_date, "2099-12-31")
        if next_bar:
            daily = daily + [next_bar[0]]
    if period == "daily" or not daily:
        return {"period": period, "items": daily}
    if period == "weekly":
        return {"period": period, "items": _aggregate_kline(daily, "W")}
    if period == "monthly":
        return {"period": period, "items": _aggregate_kline(daily, "M")}


def _aggregate_kline(daily: list, freq: str) -> list:
    """简易 周/月 K 聚合:按 (year, week) / (year, month) 分桶"""
    from datetime import datetime as dt
    if not daily:
        return []
    bucket = {}
    for bar in daily:
        d = dt.strptime(bar["trade_date"], "%Y-%m-%d")
        if freq == "W":
            key = d.strftime("%Y-W%W")
        else:
            key = d.strftime("%Y-%m")
        agg = bucket.setdefault(key, {
            "trade_date": bar["trade_date"], "open": bar["open"],
            "high": bar["high"], "low": bar["low"],
            "close": bar["close"], "volume": 0, "amount": 0,
        })
        agg["high"] = max(agg["high"], bar["high"] or agg["high"])
        agg["low"] = min(agg["low"], bar["low"] or agg["low"])
        agg["close"] = bar["close"]
        agg["volume"] = (agg["volume"] or 0) + (bar["volume"] or 0)
        agg["amount"] = (agg["amount"] or 0) + (bar["amount"] or 0)
    return sorted(bucket.values(), key=lambda x: x["trade_date"])


@router.get("/sessions/{session_id}/equity")
def equity_curve(session_id: int, user: dict = Depends(get_current_train_user)):
    """资金曲线 (2026-07-31 优化: 附带沪深 300 + 买入持有基准对比)"""
    sess = _session_for_user(user["id"], session_id)
    rows = query_all(
        "SELECT trade_date, trade_time, cash, market_value, total_equity FROM training_equity "
        "WHERE session_id = ? ORDER BY trade_date ASC, id ASC",
        (sess["id"],),
    )
    if not rows:
        return {
            "items": [],
            "initial_cash": sess["initial_cash"],
            "benchmark_hs300": [],
            "benchmark_buy_hold": [],
        }

    initial_cash = float(sess["initial_cash"] or 0)
    dates = [r[0] for r in rows]
    items = [{
        "trade_date": r[0], "trade_time": r[1],
        "cash": r[2], "market_value": r[3], "total_equity": r[4],
    } for r in rows]

    # 2026-08-04 分钟级: 基准对比按自然日去重(同一自然日多根 bar 共用一个基准日)
    is_minute = _session_period(sess) in (30, 60)
    bench_dates = sorted(set(d[:10] for d in dates)) if is_minute else dates

    # 沪深 300 同期 (拉 start_date 收盘 + 每日收盘, 按 initial_cash 折算)
    hs_start = stock_query_one(
        "SELECT close FROM index_daily WHERE code = 'sh000300' AND trade_date = ?",
        (sess["start_date"],),
    )
    benchmark_hs300 = []
    if hs_start and hs_start[0]:
        hs0 = float(hs_start[0])
        placeholders = ",".join("?" * len(bench_dates))
        for r in stock_query_all(
            f"SELECT trade_date, close FROM index_daily "
            f"WHERE code = 'sh000300' AND trade_date IN ({placeholders}) "
            f"ORDER BY trade_date ASC",
            tuple(bench_dates),
        ):
            ratio = float(r[1]) / hs0
            benchmark_hs300.append({
                "trade_date": r[0],
                "equity": round(initial_cash * ratio, 2),
            })

    # 买入持有: 用户在 start_date 用 initial_cash 全部买入, 持有到 reveal_date
    code_start = stock_query_one(
        "SELECT close FROM kline_daily WHERE code = ? AND adjust_type = 'qfq' AND trade_date = ?",
        (sess["code"], sess["start_date"]),
    )
    benchmark_buy_hold = []
    if code_start and code_start[0]:
        cs0 = float(code_start[0])
        placeholders = ",".join("?" * len(bench_dates))
        for r in stock_query_all(
            f"SELECT trade_date, close FROM kline_daily "
            f"WHERE code = ? AND adjust_type = 'qfq' AND trade_date IN ({placeholders}) "
            f"ORDER BY trade_date ASC",
            (sess["code"], *bench_dates),
        ):
            ratio = float(r[1]) / cs0
            benchmark_buy_hold.append({
                "trade_date": r[0],
                "equity": round(initial_cash * ratio, 2),
            })

    return {
        "items": items,
        "initial_cash": initial_cash,
        "benchmark_hs300": benchmark_hs300,    # 沪深 300 同期
        "benchmark_buy_hold": benchmark_buy_hold,  # 买入持有
    }


@router.post("/sessions/{session_id}/trade")
@limiter.limit("60/minute")
def trade(session_id: int, req: TradeOrderRequest, request: Request, response: Response, user: dict = Depends(get_current_train_user)):
    """下单:买入/卖出 — 限价撮合(简单地按当前 bar close 撮合)"""
    sess = _session_for_user(user["id"], session_id)
    if sess["status"] != "active":
        raise HTTPException(status_code=400, detail="该训练已结束")
    side = req.side.upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side 必须是 BUY/SELL")

    # 2026-08-04 分钟级: 分钟模式 current_dt 精确到 bar(reveal_time), 日线用 reveal_date
    period = _session_period(sess)
    is_minute = period in (30, 60)
    if is_minute:
        current_dt = sess.get("reveal_time") or sess["reveal_date"] or sess["start_date"]
    else:
        current_dt = sess["reveal_date"] or sess["start_date"]
    # 撮合价取<current_dt 及之后>的第一根 bar(若 reveal 是节假日/停牌则下一根)
    if is_minute:
        mbars = _minute_bars(
            sess["code"], period,
            current_dt, f"{sess['end_date']} 23:59:59",
        )
        bar_row = (
            (mbars[0]["trade_time"], mbars[0]["open"], mbars[0]["high"],
             mbars[0]["low"], mbars[0]["close"])
            if mbars else None
        )
    else:
        bar_row = stock_query_one(
            "SELECT trade_date, open, high, low, close FROM kline_daily "
            "WHERE code = ? AND adjust_type = 'qfq' AND trade_date >= ? "
            "ORDER BY trade_date ASC LIMIT 1",
            (sess["code"], current_dt),
        )
    if not bar_row:
        raise HTTPException(status_code=400, detail="当前还未揭示 K 线")
    # bar: (open, high, low, close)
    bar = (bar_row[1], bar_row[2], bar_row[3], bar_row[4])

    # 2026-07-31 优化: 涨跌停校验 (A 股规则)
    # 创业板(30x)/科创板(688) 限 ±20%, ST 股限 ±5%, 其他 ±10%
    # 2026-08-04 分钟级: 分钟模式昨收用"前一根分钟 bar close", 无则 fallback kline_daily 前一日
    if is_minute:
        pmin = [
            b for b in _minute_bars(
                sess["code"], period,
                sess["start_date"], f"{bar_row[0]} 23:59:59",
                order="DESC",
            )
            if b["trade_time"] < bar_row[0]  # 严格取当前 bar 之前的一根
        ]
        pre_min_row = (pmin[0]["close"],) if pmin else None
        if pre_min_row and pre_min_row[0]:
            pre_close = float(pre_min_row[0])
        else:
            pre_daily_row = stock_query_one(
                "SELECT close FROM kline_daily "
                "WHERE code = ? AND adjust_type = 'qfq' AND trade_date < ? "
                "ORDER BY trade_date DESC LIMIT 1",
                (sess["code"], bar_row[0][:10]),
            )
            pre_close = float(pre_daily_row[0]) if pre_daily_row and pre_daily_row[0] else float(bar[3])
    else:
        pre_close_row = stock_query_one(
            "SELECT close FROM kline_daily "
            "WHERE code = ? AND adjust_type = 'qfq' AND trade_date < ? "
            "ORDER BY trade_date DESC LIMIT 1",
            (sess["code"], bar_row[0]),
        )
        pre_close = float(pre_close_row[0]) if pre_close_row and pre_close_row[0] else float(bar[3])
    name = (sess.get("name") or "").upper()
    code = sess.get("code") or ""
    is_st = "ST" in name
    is_chinext = code.startswith("30")
    is_kcb = code.startswith("688")
    if is_chinext or is_kcb:
        limit_pct = 0.20
    elif is_st:
        limit_pct = 0.05
    else:
        limit_pct = 0.10
    upper_limit = pre_close * (1 + limit_pct)
    lower_limit = pre_close * (1 - limit_pct)
    # 实际撮合 bar: 分钟模式 trade_date=自然日, trade_time=完整 bar; 日线 trade_date=交易日
    trade_date = bar_row[0][:10] if is_minute else bar_row[0]
    trade_time_val = bar_row[0] if is_minute else None

    # 撮合价默认按 open(P0-4 修复,2026-07-31 起,符合"次日开盘成交"的真实体感)
    price = req.price if req.price else float(bar[0])
    if price <= 0:
        raise HTTPException(status_code=400, detail="价格非法")

    # 2026-07-31 优化: 涨跌停撮合校验
    # 1) 限价单买入价 > 涨停价 → 撮合失败 (无法买入)
    if side == "BUY" and price > upper_limit + 0.001:
        raise HTTPException(
            status_code=400,
            detail=(
                f"限价 ¥{price:.2f} 超过涨停价 ¥{upper_limit:.2f} (昨收 ¥{pre_close:.2f} × {1+limit_pct:.0%}),"
                f"无法按此价买入"
            ),
        )
    # 2) 限价单卖出价 < 跌停价 → 撮合失败 (无法卖出)
    if side == "SELL" and price < lower_limit - 0.001:
        raise HTTPException(
            status_code=400,
            detail=(
                f"限价 ¥{price:.2f} 低于跌停价 ¥{lower_limit:.2f} (昨收 ¥{pre_close:.2f} × {1-limit_pct:.0%}),"
                f"无法按此价卖出"
            ),
        )

    with get_conn() as conn:
        if side == "BUY":
            # 优先使用前端传入的 quantity(按股买入);若未给再退回金额推算
            if req.quantity and req.quantity > 0:
                qty = int(req.quantity // 100) * 100
                if qty <= 0:
                    raise HTTPException(status_code=400, detail="买入股数必须为 100 整数倍")
            else:
                amount_budget = req.amount or sess["per_trade_amount"]
                if amount_budget <= 0:
                    raise HTTPException(status_code=400, detail="买入金额必须 > 0")
                qty = int(amount_budget // (price * 100)) * 100
                if qty <= 0:
                    raise HTTPException(status_code=400, detail="金额不足以买入 1 手 (100 股)")
            trade_amount = qty * price
            fees = _calc_total_fees(trade_amount, qty, sess, "BUY")
            total_pay = trade_amount + fees["total_fee"]

            # 现金 = 用户钱包余额(共用)
            cash = _wallet_for_update_in_conn(conn, user["id"])
            if cash < total_pay:
                raise HTTPException(
                    status_code=402,
                    detail=f"现金不足,可用 {cash:.2f} 元,需要 {total_pay:.2f}",
                )

            # 检查分仓
            pos_cnt = conn.execute(
                "SELECT COUNT(*) FROM training_position WHERE session_id = ? AND quantity > 0",
                (sess["id"],),
            ).fetchone()[0]
            if pos_cnt >= sess["max_positions"] and not sess["allow_split"]:
                # 检查是否已经有这只
                exist = conn.execute(
                    "SELECT 1 FROM training_position WHERE session_id = ? AND code = ? AND quantity > 0",
                    (sess["id"], sess["code"]),
                ).fetchone()
                if not exist:
                    raise HTTPException(
                        status_code=400,
                        detail=f"已达最大持仓数 {sess['max_positions']}",
                    )

            # 写订单
            # 2026-07-31 优化: 限价单模式 (req.pending=true)
            is_pending_order = bool(req.pending) and (
                price > float(bar[1]) + 0.001 or  # 限价 > bar.high (即上挂单)
                price < float(bar[0]) - 0.001      # 限价 < bar.low  (下挂单, 用 open 近似)
            )
            # 简化: 限价 ≤ bar.high 且 ≥ bar.low 时认为当日能成交
            if req.pending:
                if price < float(bar[2]) - 0.001 or price > float(bar[1]) + 0.001:
                    is_pending_order = True
                else:
                    is_pending_order = False  # 限价在 bar 范围内, 立即成交
            else:
                is_pending_order = False

            cur = conn.execute(
                """INSERT INTO training_order(
                    session_id, user_id, trade_date, trade_time, side, price, quantity, amount,
                    commission, stamp_tax, transfer_fee, total_fee, pending_status
                ) VALUES(?, ?, ?, ?, 'BUY', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sess["id"], user["id"], trade_date, trade_time_val,
                 price, qty, trade_amount,
                 fees["commission"], fees["stamp_tax"], fees["transfer_fee"], fees["total_fee"],
                 "pending" if is_pending_order else "filled"),
            )
            order_id = cur.lastrowid

            if is_pending_order:
                # 限价单未立即成交: 写 note + 不扣钱不更新持仓
                conn.execute(
                    "UPDATE training_order SET note = ? WHERE id = ?",
                    (f"限价单,等待 {req.pending_ttl} 个交易日内触及 ¥{price:.2f} 后成交", order_id),
                )
                _record_event(
                    conn, sess["id"], user["id"], "buy", trade_date,
                    payload={
                        "order_id": order_id, "code": sess["code"],
                        "qty": qty, "price": price, "total_pay": total_pay,
                        "fees": fees, "pending": True, "pending_ttl": req.pending_ttl,
                    },
                    snapshot={"prev_balance": cash, "is_pending": True},
                )
            else:
                # 立即成交: 更新持仓 + 扣钱包
                # 更新持仓:avg_cost 含买入手续费
                row = conn.execute(
                    "SELECT quantity, avg_cost FROM training_position WHERE session_id = ? AND code = ?",
                    (sess["id"], sess["code"]),
                ).fetchone()
                if row:
                    old_qty, old_avg = row
                    old_cost_basis = old_qty * (old_avg or 0)
                    new_buy_cost = qty * price + fees["total_fee"]
                    new_qty = old_qty + qty
                    new_avg = (old_cost_basis + new_buy_cost) / new_qty
                    conn.execute(
                        "UPDATE training_position SET quantity = ?, avg_cost = ?, "
                        "updated_at = datetime('now', 'localtime') WHERE session_id = ? AND code = ?",
                        (new_qty, new_avg, sess["id"], sess["code"]),
                    )
                else:
                    full_cost = qty * price + fees["total_fee"]
                    avg_cost_with_fee = full_cost / qty
                    conn.execute(
                        "INSERT INTO training_position(session_id, user_id, code, quantity, avg_cost) "
                        "VALUES(?, ?, ?, ?, ?)",
                        (sess["id"], user["id"], sess["code"], qty, avg_cost_with_fee),
                    )
                # 钱包扣款
                conn.execute(
                    "UPDATE training_wallet "
                    "SET balance = balance - ?, total_spent = total_spent + ?, "
                    "    updated_at = datetime('now','localtime') "
                    "WHERE user_id = ? AND balance >= ?",
                    (total_pay, total_pay, user["id"], total_pay),
                )
                # P1-12: 记录 buy 事件
                _record_event(
                    conn, sess["id"], user["id"], "buy", trade_date,
                    payload={
                        "order_id": order_id, "code": sess["code"],
                        "qty": qty, "price": price, "total_pay": total_pay,
                        "fees": fees, "pending": False,
                    },
                    snapshot={"prev_balance": cash},
                )

        else:  # SELL
            if not req.quantity or req.quantity <= 0:
                raise HTTPException(status_code=400, detail="请填写卖出股数")
            qty = int(req.quantity)
            # 2026-08-04 修复: snapshot 记录 prev_balance 需要当前余额(BUY 分支已读,SELL 分支此前漏读)
            cash = _wallet_for_update_in_conn(conn, user["id"])
            row = conn.execute(
                "SELECT quantity, avg_cost FROM training_position WHERE session_id = ? AND code = ?",
                (sess["id"], sess["code"]),
            ).fetchone()
            if not row or row[0] < qty:
                raise HTTPException(status_code=400, detail="可卖股数不足")

            # T+1 校验(P0-4 修复,2026-07-31 起):A 股真实规则,
            # 当日买入次日才能卖。"今天买的未卖股数" = 今日 BUY − 今日 SELL
            today_buy_qty = (conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) FROM training_order "
                "WHERE session_id = ? AND user_id = ? AND side = 'BUY' AND trade_date = ?",
                (sess["id"], user["id"], trade_date),
            ).fetchone() or (0,))[0] or 0
            today_sell_qty = (conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) FROM training_order "
                "WHERE session_id = ? AND user_id = ? AND side = 'SELL' AND trade_date = ?",
                (sess["id"], user["id"], trade_date),
            ).fetchone() or (0,))[0] or 0
            t1_locked = max(0, int(today_buy_qty) - int(today_sell_qty))
            sellable = int(row[0]) - t1_locked
            if sellable < qty:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"T+1 限制:今日({trade_date})新买入的 {t1_locked} 股需次日才能卖,"
                        f"当前可卖 {sellable} 股,本次请求卖 {qty} 股"
                    ),
                )

            trade_amount = qty * price
            fees = _calc_total_fees(trade_amount, qty, sess, "SELL")
            # FIFO 真实实现盈亏: 卖出价 - 买入成本 - 卖出手续费 - 分摊的买入费用
            cost_basis, fee_proportion = _fifo_cost_basis(
                user["id"], sess["id"], qty
            )
            realized_pnl = trade_amount - fees["total_fee"] - cost_basis - fee_proportion

            # 2026-07-31 优化: 限价单模式
            if req.pending:
                if price < float(bar[2]) - 0.001 or price > float(bar[1]) + 0.001:
                    is_pending_order = True
                else:
                    is_pending_order = False
            else:
                is_pending_order = False

            cur = conn.execute(
                """INSERT INTO training_order(
                    session_id, user_id, trade_date, trade_time, side, price, quantity, amount,
                    commission, stamp_tax, transfer_fee, total_fee, realized_pnl, pending_status
                ) VALUES(?, ?, ?, ?, 'SELL', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sess["id"], user["id"], trade_date, trade_time_val,
                 price, qty, trade_amount,
                 fees["commission"], fees["stamp_tax"], fees["transfer_fee"],
                 fees["total_fee"], round(realized_pnl, 2),
                 "pending" if is_pending_order else "filled"),
            )
            order_id = cur.lastrowid

            if is_pending_order:
                conn.execute(
                    "UPDATE training_order SET note = ? WHERE id = ?",
                    (f"限价单,等待 {req.pending_ttl} 个交易日内触及 ¥{price:.2f} 后成交", order_id),
                )
                _record_event(
                    conn, sess["id"], user["id"], "sell", trade_date,
                    payload={
                        "order_id": order_id, "code": sess["code"],
                        "qty": qty, "price": price, "net_recv": trade_amount - fees["total_fee"],
                        "fees": fees, "pending": True, "pending_ttl": req.pending_ttl,
                    },
                    snapshot={"prev_balance": cash, "avg_cost": row[1] if row else 0, "is_pending": True},
                )
            else:
                # 立即成交: 更新持仓 + 加钱包
                new_qty = row[0] - qty
                if new_qty == 0:
                    conn.execute(
                        "DELETE FROM training_position WHERE session_id = ? AND code = ?",
                        (sess["id"], sess["code"]),
                    )
                else:
                    conn.execute(
                        "UPDATE training_position SET quantity = ?, updated_at = datetime('now','localtime') "
                        "WHERE session_id = ? AND code = ?",
                        (new_qty, sess["id"], sess["code"]),
                    )
                net_recv = trade_amount - fees["total_fee"]
                conn.execute(
                    "UPDATE training_wallet "
                    "SET balance = balance + ?, updated_at = datetime('now','localtime') "
                    "WHERE user_id = ?",
                    (net_recv, user["id"]),
                )
                _record_event(
                    conn, sess["id"], user["id"], "sell", trade_date,
                    payload={
                        "order_id": order_id, "code": sess["code"],
                        "qty": qty, "price": price, "net_recv": net_recv,
                        "fees": fees, "pending": False,
                    },
                    snapshot={"prev_balance": cash, "avg_cost": row[1] if row else 0},
                )

    # 返回最新视图
    updated_sess = _session_for_user(user["id"], session_id)
    view = _build_session_view(updated_sess)
    view["last_order_id"] = order_id
    return view


@router.post("/sessions/{session_id}/finish")
def finish(session_id: int, user: dict = Depends(get_current_train_user)):
    """主动结束训练(返回当前权益曲线)"""
    cur = execute(
        "UPDATE training_session SET status='finished', updated_at=datetime('now','localtime') "
        "WHERE id = ? AND user_id = ? AND status='active'",
        (session_id, user["id"]),
    )
    # execute 是用普通连接, 返回的是 sqlite3.Cursor, 检查 rowcount
    affected = getattr(cur, "rowcount", 0) or 0
    if affected == 0:
        # 区分: 是状态已结束还是 session 不存在
        row = query_one(
            "SELECT status FROM training_session WHERE id = ? AND user_id = ?",
            (session_id, user["id"]),
        )
        if not row:
            raise HTTPException(status_code=404, detail="训练会话不存在")
        # 已经是 finished 了 — 幂等返回当前视图
    else:
        # 2026-07-31 P1-12: 记录事件
        try:
            execute(
                "INSERT INTO training_event(session_id, user_id, event_type, payload_json) "
                "VALUES(?, ?, 'finish', ?)",
                (session_id, user["id"], _json.dumps({"finished_at": datetime.now().isoformat()})),
            )
        except Exception as e:
            log.warning(f"[rollback] 记 finish event 失败: {e}")
    return get_session(session_id, user=user)


# =========================================================
# 2026-07-31 P1-12: 事件流 + 撤销
# =========================================================
import json as _json
def _record_event(
    conn,
    session_id: int,
    user_id: int,
    event_type: str,
    trade_date: Optional[str] = None,
    payload: Optional[dict] = None,
    snapshot: Optional[dict] = None,
    note: Optional[str] = None,
) -> None:
    """记录一条训练事件(2026-07-31 P1-12 启用)。失败仅警告,不阻断主业务。"""
    try:
        conn.execute(
            "INSERT INTO training_event("
            "  session_id, user_id, event_type, trade_date,"
            "  payload_json, snapshot_json, note"
            ") VALUES(?, ?, ?, ?, ?, ?, ?)",
            (
                session_id, user_id, event_type, trade_date,
                _json.dumps(payload or {}, ensure_ascii=False),
                _json.dumps(snapshot or {}, ensure_ascii=False),
                note or "",
            ),
        )
    except Exception as e:
        log.warning(f"[event] 记 {event_type} 事件失败: {e}")


@router.post("/sessions/{session_id}/rollback")
@limiter.limit("20/minute")
def rollback(session_id: int, request: Request, response: Response,
             user: dict = Depends(get_current_train_user)):
    """撤销最后一步操作(2026-07-31 P1-12)。

    支持撤销的事件类型(按 event_type):
      - buy   : 删除订单 + 回滚持仓 + 加回钱包
      - sell  : 删除订单 + 加回持仓 + 扣回钱包
      - advance: 删除该次 advance 产生的 equity 快照 + 回滚 reveal_date
      - finish: 改回 active
    """
    sess = _session_for_user(user["id"], session_id)

    # 找最后一条非 rollback 事件
    last = query_one(
        "SELECT id, event_type, trade_date, payload_json, snapshot_json "
        "FROM training_event WHERE session_id = ? AND user_id = ? "
        "AND event_type != 'rollback' "
        "ORDER BY id DESC LIMIT 1",
        (sess["id"], user["id"]),
    )
    if not last:
        raise HTTPException(status_code=400, detail="没有可撤销的事件")
    last_id, event_type, trade_date, payload_str, snapshot_str = last
    try:
        payload = _json.loads(payload_str or "{}")
        snapshot = _json.loads(snapshot_str or "{}")
    except Exception:
        payload, snapshot = {}, {}

    with get_conn() as conn:
        if event_type == "buy":
            # 删除订单 + 回滚持仓 + 加回钱包
            order_id = payload.get("order_id")
            total_pay = float(payload.get("total_pay", 0))
            code = payload.get("code") or sess["code"]
            qty = int(payload.get("qty", 0))
            if not order_id:
                raise HTTPException(status_code=400, detail="事件缺 order_id, 无法撤销")
            conn.execute("DELETE FROM training_order WHERE id = ?", (order_id,))
            # 持仓回滚:减掉 qty
            row = conn.execute(
                "SELECT quantity, avg_cost FROM training_position "
                "WHERE session_id = ? AND code = ?",
                (sess["id"], code),
            ).fetchone()
            if row:
                old_qty, _old_avg = row
                new_qty = old_qty - qty
                if new_qty <= 0:
                    conn.execute(
                        "DELETE FROM training_position WHERE session_id = ? AND code = ?",
                        (sess["id"], code),
                    )
                else:
                    # avg_cost 不变(只是减仓), 实际更精确应重算但 FIFO 已实现盈亏
                    conn.execute(
                        "UPDATE training_position SET quantity = ?, "
                        "updated_at = datetime('now', 'localtime') "
                        "WHERE session_id = ? AND code = ?",
                        (new_qty, sess["id"], code),
                    )
            # 钱包加回
            conn.execute(
                "UPDATE training_wallet SET balance = balance + ?, "
                "total_spent = MAX(0, total_spent - ?), "
                "updated_at = datetime('now', 'localtime') WHERE user_id = ?",
                (total_pay, total_pay, user["id"]),
            )
            _record_event(
                conn, sess["id"], user["id"], "rollback", trade_date,
                payload={"of_event_id": last_id, "of_event_type": "buy",
                         "order_id": order_id, "qty": qty, "refund": total_pay},
            )

        elif event_type == "sell":
            # 删除订单 + 加回持仓 + 扣回钱包
            order_id = payload.get("order_id")
            net_recv = float(payload.get("net_recv", 0))
            code = payload.get("code") or sess["code"]
            qty = int(payload.get("qty", 0))
            if not order_id:
                raise HTTPException(status_code=400, detail="事件缺 order_id, 无法撤销")
            conn.execute("DELETE FROM training_order WHERE id = ?", (order_id,))
            # 持仓加回
            row = conn.execute(
                "SELECT quantity, avg_cost FROM training_position "
                "WHERE session_id = ? AND code = ?",
                (sess["id"], code),
            ).fetchone()
            # 撤销时使用 snapshot 里的 avg_cost(原 SELL 前的持仓成本基础)
            prev_avg = float(snapshot.get("avg_cost") or 0)
            if row:
                old_qty = row[0]
            else:
                old_qty = 0
            new_qty = old_qty + qty
            if prev_avg <= 0:
                # 无旧 avg_cost 记录 → 用 0 (实际应拒绝;但避免崩)
                prev_avg = 0.0
            conn.execute(
                "INSERT INTO training_position(session_id, user_id, code, quantity, avg_cost) "
                "VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(session_id, code) DO UPDATE SET "
                "  quantity = excluded.quantity, "
                "  avg_cost = excluded.avg_cost, "
                "  updated_at = datetime('now', 'localtime')",
                (sess["id"], user["id"], code, new_qty, prev_avg),
            )
            # 钱包扣回
            conn.execute(
                "UPDATE training_wallet SET balance = balance - ?, "
                "updated_at = datetime('now', 'localtime') WHERE user_id = ?",
                (net_recv, user["id"]),
            )
            _record_event(
                conn, sess["id"], user["id"], "rollback", trade_date,
                payload={"of_event_id": last_id, "of_event_type": "sell",
                         "order_id": order_id, "qty": qty, "refund": net_recv},
            )

        elif event_type == "advance":
            # 删除该次 advance 产生的 equity 快照 + 回滚 reveal_date/reveal_time
            days = int(payload.get("days", 0))
            advance_dates = payload.get("advance_dates", [])
            # 2026-08-04 分钟级: advance_dates 为完整 trade_time(含 ':')→ 按 trade_time 删;
            # 日线为 trade_date → 按 trade_date 删。
            if advance_dates:
                placeholders = ",".join("?" * len(advance_dates))
                if any(":" in str(a) for a in advance_dates):
                    conn.execute(
                        f"DELETE FROM training_equity "
                        f"WHERE session_id = ? AND trade_time IN ({placeholders})",
                        (sess["id"], *advance_dates),
                    )
                else:
                    conn.execute(
                        f"DELETE FROM training_equity "
                        f"WHERE session_id = ? AND trade_date IN ({placeholders})",
                        (sess["id"], *advance_dates),
                    )
            # 回滚 reveal_time(分钟模式) + reveal_date(两者)
            prev_reveal = snapshot.get("prev_reveal_date") or sess["start_date"]
            prev_reveal_time = snapshot.get("prev_reveal_time")
            if prev_reveal_time:
                conn.execute(
                    "UPDATE training_session SET reveal_date = ?, reveal_time = ?, "
                    "updated_at = datetime('now', 'localtime') WHERE id = ?",
                    (prev_reveal_time[:10], prev_reveal_time, sess["id"]),
                )
            else:
                conn.execute(
                    "UPDATE training_session SET reveal_date = ?, "
                    "updated_at = datetime('now', 'localtime') WHERE id = ?",
                    (prev_reveal, sess["id"]),
                )
            _record_event(
                conn, sess["id"], user["id"], "rollback", trade_date,
                payload={"of_event_id": last_id, "of_event_type": "advance",
                         "days": days, "prev_reveal_date": prev_reveal,
                         "prev_reveal_time": prev_reveal_time},
            )

        elif event_type == "finish":
            conn.execute(
                "UPDATE training_session SET status = 'active', "
                "updated_at = datetime('now', 'localtime') WHERE id = ?",
                (sess["id"],),
            )
            _record_event(
                conn, sess["id"], user["id"], "rollback", trade_date,
                payload={"of_event_id": last_id, "of_event_type": "finish"},
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"事件类型 {event_type} 不支持撤销",
            )

    return get_session(session_id, user=user)
