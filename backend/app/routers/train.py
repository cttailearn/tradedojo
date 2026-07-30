"""
K线交易训练 —— 业务主路由
- 随机选股 / 开训练场
- 时间推进(逐日揭示 K 线)
- 下单撮合(买入/卖出)
- 持仓 / 资金 / 成交记录
"""
import logging
import random
import sqlite3
import math
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.deps_train import get_current_train_user
from app.models import (
    AdvanceRequest,
    TradeOrderRequest,
    TrainingSessionInfo,
    TrainingSetupRequest,
)
from app.config import settings
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
    """
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
    rows = stock_query_all(
        f"SELECT s.code, s.name, s.industry, s.market FROM stock_list s "
        f"WHERE {base_where_sql} ORDER BY s.code ASC",
        tuple(params),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="没有符合条件的股票(请放宽过滤)")
    random.shuffle(rows)

    def _has_enough_kline(code: str) -> bool:
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


def _kline_in_window(code: str, start_date: str, end_date: str) -> list:
    """读取某只股票在 [start, end] 区间的 K 线 (stock.db)"""
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


SESSION_COLS = (
    "id", "user_id", "code", "name", "industry", "market",
    "start_date", "end_date", "lookback_months", "initial_cash",
    "commission_rate", "min_commission", "stamp_tax", "transfer_fee",
    "allow_split", "max_positions", "per_trade_amount", "allow_chinext",
    "allow_st", "allow_kcb", "allow_bj", "total_fee_paid", "status",
    "reveal_date", "created_at", "updated_at",
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


def _build_session_view(session: dict) -> dict:
    """基于数据库拼装完整的会话视图(用于前端)"""
    sid = session["id"]
    code = session["code"]
    user_id = session["user_id"]

    # 已揭示 K 线:
    #   - 从 session.start_date - lookback_months(历史回看)开始
    #   - 到 current_date(逐日推进揭示到这里)为止
    from datetime import datetime as _dt, timedelta as _td
    current_dt = session.get("reveal_date") or session["start_date"]
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
    revealed = _kline_in_window(code, lookback_start, current_dt)
    # 若 reveal_date 是非交易日,把下一个交易日 bar 拼上,作为"当前可见 bar"
    if revealed and revealed[-1]["trade_date"] < current_dt:
        next_bar = _kline_in_window(code, current_dt, "2099-12-31")
        if next_bar:
            revealed = revealed + [next_bar[0]]
    current_bar = revealed[-1] if revealed else None

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

    # 现金:初始资金 - 已支付金额 + 累计实现盈亏(从订单推断)
    orders = query_all(
        "SELECT id, trade_date, side, price, quantity, amount, "
        "       commission, stamp_tax, transfer_fee, total_fee, realized_pnl "
        "FROM training_order WHERE session_id = ? ORDER BY id DESC LIMIT 50",
        (sid,),
    )
    paid_buy = query_one(
        "SELECT COALESCE(SUM(amount+total_fee),0) FROM training_order "
        "WHERE session_id = ? AND side = 'BUY'",
        (sid,),
    )[0] or 0
    recv_sell = query_one(
        "SELECT COALESCE(SUM(amount-total_fee),0) FROM training_order "
        "WHERE session_id = ? AND side = 'SELL'",
        (sid,),
    )[0] or 0
    cash = session["initial_cash"] - paid_buy + recv_sell
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
    }


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


@router.post("/sessions/start")
@limiter.limit("20/minute")
def start_session(req: TrainingSetupRequest, request: Request, response: Response, user: dict = Depends(get_current_train_user)):
    """发起一场训练:消费钱包余额、随机选股、写入 session"""
    # 训练费统一在 app/utils.calc_session_cost,前端用 frontend/src/utils/trainFee.js
    session_cost = calc_session_cost(req.start_date, req.end_date, req.initial_cash)

    with get_conn() as conn:
        # 原子化扣费: UPDATE WHERE balance >= ? 看 rowcount
        # 避免并发扣减导致超额
        cur = conn.execute(
            "UPDATE training_wallet SET balance = balance - ?, "
            "total_spent = total_spent + ?, "
            "updated_at = datetime('now','localtime') "
            "WHERE user_id = ? AND balance >= ?",
            (session_cost, session_cost, user["id"], session_cost),
        )
        if cur.rowcount == 0:
            # 余额不足或钱包不存在
            row = conn.execute(
                "SELECT balance FROM training_wallet WHERE user_id = ?",
                (user["id"],),
            ).fetchone()
            cur_bal = float(row[0] or 0) if row else 0.0
            raise HTTPException(
                status_code=402,
                detail=f"训练资金不足,本次需要 {session_cost:.2f} 元,当前余额 {cur_bal:.2f} 元",
            )

        # 重新读取扣后余额(用于返回)
        balance_row = conn.execute(
            "SELECT balance FROM training_wallet WHERE user_id = ?",
            (user["id"],),
        ).fetchone()
        balance_after = float(balance_row[0] or 0)

        # 随机选股
        req_sub = TrainingSetupRequest(**req.model_dump())
        stock = _pick_random_stock(req_sub)

        # 初始揭示 = 训练开始日,但若 start_date 是节假日/周末没有 K 线,
        # 自动顺延到该股票的下个实际交易日,否则前端会拿到空 K 线图
        # 注意:用户会话在 user_tx 内,但 kline_daily 在 stock.db,必须单独查
        cur = stock_query_one(
            "SELECT MIN(trade_date) FROM kline_daily "
            "WHERE code = ? AND adjust_type = 'qfq' AND trade_date >= ?",
            (stock["code"], req.start_date),
        )
        current_dt = (cur[0] if cur and cur[0] else req.start_date)

        cur = conn.execute(
            """INSERT INTO training_session(
                user_id, code, name, industry, market,
                start_date, end_date, lookback_months, initial_cash,
                commission_rate, min_commission, stamp_tax, transfer_fee,
                allow_split, max_positions, per_trade_amount,
                allow_chinext, allow_st, allow_kcb, allow_bj,
                total_fee_paid, status, reveal_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
            (user["id"], stock["code"], stock["name"], stock["industry"], stock["market"],
             req.start_date, req.end_date, req.lookback_months, req.initial_cash,
             req.commission_rate, req.min_commission, req.stamp_tax, req.transfer_fee,
             int(req.allow_split), req.max_positions, req.per_trade_amount,
             int(req.allow_chinext), int(req.allow_st), int(req.allow_kcb), int(req.allow_bj),
             session_cost, current_dt),
        )
        sid = cur.lastrowid
        # 初始权益 = initial_cash
        conn.execute(
            "INSERT INTO training_equity(session_id, trade_date, cash, market_value, total_equity) "
            "VALUES(?, ?, ?, 0, ?)",
            (sid, current_dt, req.initial_cash, req.initial_cash),
        )

    # 重新读取
    row = query_one("SELECT * FROM training_session WHERE id = ?", (sid,))
    session = dict(zip(SESSION_COLS, row))
    view = _build_session_view(session)
    view["session_cost"] = session_cost
    view["wallet_balance_after"] = balance_after
    return view


@router.get("/sessions/{session_id}")
def get_session(session_id: int, user: dict = Depends(get_current_train_user)):
    row = query_one("SELECT * FROM training_session WHERE id = ? AND user_id = ?",
                    (session_id, user["id"]))
    if not row:
        raise HTTPException(status_code=404, detail="训练会话不存在")
    session = dict(zip(SESSION_COLS, row))
    return _build_session_view(session)


@router.post("/sessions/{session_id}/advance")
@limiter.limit("60/minute")
def advance(session_id: int, req: AdvanceRequest, request: Request, response: Response, user: dict = Depends(get_current_train_user)):
    """时间推进:把 current_date 向后推 N 个交易日;返回新的视图"""
    sess = _session_for_user(user["id"], session_id)
    if sess["status"] != "active":
        raise HTTPException(status_code=400, detail="该训练已结束")

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

    # 现金来自订单:对所有 BUY/SELL 在当前时刻的累加只与"订单"有关,不随时间变化
    paid_buy = query_one(
        "SELECT COALESCE(SUM(amount+total_fee),0) FROM training_order "
        "WHERE session_id = ? AND side = 'BUY'",
        (sess["id"],),
    )[0] or 0
    recv_sell = query_one(
        "SELECT COALESCE(SUM(amount-total_fee),0) FROM training_order "
        "WHERE session_id = ? AND side = 'SELL'",
        (sess["id"],),
    )[0] or 0
    cash = sess["initial_cash"] - paid_buy + recv_sell

    # 一次拉所有持仓代码的 close 列(逐日 close),用于插每个揭示日的权益快照
    pos_codes = query_all(
        "SELECT code FROM training_position WHERE session_id = ? AND quantity > 0",
        (sess["id"],),
    )
    if pos_codes:
        code_list = [c[0] for c in pos_codes]
        placeholders = ",".join("?" * len(code_list))
        close_map = {}   # code -> { trade_date -> close }
        for r in stock_query_all(
            f"SELECT code, trade_date, close FROM kline_daily "
            f"WHERE code IN ({placeholders}) AND adjust_type = 'qfq' "
            f"  AND trade_date IN ({','.join('?'*len(advance_dates))})",
            tuple(code_list) + tuple(advance_dates),
        ):
            close_map.setdefault(r[0], {})[r[1]] = r[2]
    else:
        close_map = {}

    with get_conn() as conn:
        # 每个揭示日插 1 条 equity 快照,曲线连续
        for d in advance_dates:
            mv = 0.0
            for c in close_map:
                # 持仓仅显示在 start_date 之后开仓的部分;这里用当前持仓量*该日 close
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
            conn.execute(
                "INSERT INTO training_equity(session_id, trade_date, cash, market_value, total_equity) "
                "VALUES(?, ?, ?, ?, ?)",
                (sess["id"], d, cash, mv, cash + mv),
            )

    return get_session(session_id, user=user)


@router.get("/sessions/{session_id}/kline")
def session_kline(session_id: int, period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
                  user: dict = Depends(get_current_train_user)):
    """返回已揭示的日/周/月 K 线(含 lookback_months 历史回看)"""
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
    sess = _session_for_user(user["id"], session_id)
    rows = query_all(
        "SELECT trade_date, cash, market_value, total_equity FROM training_equity "
        "WHERE session_id = ? ORDER BY trade_date ASC, id ASC",
        (sess["id"],),
    )
    return {
        "items": [{
            "trade_date": r[0], "cash": r[1],
            "market_value": r[2], "total_equity": r[3],
        } for r in rows],
        "initial_cash": sess["initial_cash"],
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

    current_dt = sess["reveal_date"] or sess["start_date"]
    # 撮合价取<reveal_date 及之后>的第一根 bar(若 reveal 是节假日则下一交易日)
    bar_row = stock_query_one(
        "SELECT trade_date, open, high, low, close FROM kline_daily "
        "WHERE code = ? AND adjust_type = 'qfq' AND trade_date >= ? "
        "ORDER BY trade_date ASC LIMIT 1",
        (sess["code"], current_dt),
    )
    if not bar_row:
        raise HTTPException(status_code=400, detail="当前还未揭示 K 线")
    bar = (bar_row[1], bar_row[2], bar_row[3], bar_row[4])
    trade_date = bar_row[0]   # 实际撮合交易日(可能不是 reveal_date 本身)

    price = req.price if req.price else float(bar[3])  # 撮合价
    if price <= 0:
        raise HTTPException(status_code=400, detail="价格非法")

    with get_conn() as conn:
        if side == "BUY":
            # 股数 = 金额 / 价格,按 100 取整
            amount_budget = req.amount or sess["per_trade_amount"]
            if amount_budget <= 0:
                raise HTTPException(status_code=400, detail="买入金额必须 > 0")
            qty = int(amount_budget // (price * 100)) * 100
            if qty <= 0:
                raise HTTPException(status_code=400, detail="金额不足以买入 1 手 (100 股)")
            trade_amount = qty * price
            fees = _calc_total_fees(trade_amount, qty, sess, "BUY")
            total_pay = trade_amount + fees["total_fee"]

            # 检查现金
            paid_buy = conn.execute(
                "SELECT COALESCE(SUM(amount+total_fee),0) FROM training_order "
                "WHERE session_id = ? AND side = 'BUY'",
                (sess["id"],),
            ).fetchone()[0] or 0
            recv_sell = conn.execute(
                "SELECT COALESCE(SUM(amount-total_fee),0) FROM training_order "
                "WHERE session_id = ? AND side = 'SELL'",
                (sess["id"],),
            ).fetchone()[0] or 0
            cash = sess["initial_cash"] - paid_buy + recv_sell
            if cash < total_pay:
                raise HTTPException(status_code=400, detail=f"现金不足,可用 {cash:.2f} 元,需要 {total_pay:.2f}")

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
                    raise HTTPException(status_code=400, detail=f"已达最大持仓数 {sess['max_positions']}")

            # 写订单
            cur = conn.execute(
                """INSERT INTO training_order(
                    session_id, user_id, trade_date, side, price, quantity, amount,
                    commission, stamp_tax, transfer_fee, total_fee
                ) VALUES(?, ?, ?, 'BUY', ?, ?, ?, ?, ?, ?, ?)""",
                (sess["id"], user["id"], trade_date,
                 price, qty, trade_amount,
                 fees["commission"], fees["stamp_tax"], fees["transfer_fee"], fees["total_fee"]),
            )
            order_id = cur.lastrowid

            # 更新持仓:avg_cost 含买入手续费(更符合实际成本)
            # new_avg = (old_cost_basis + new_buy_cost) / new_qty
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
                # 首次买入:把买入费用计入成本
                full_cost = qty * price + fees["total_fee"]
                avg_cost_with_fee = full_cost / qty
                conn.execute(
                    "INSERT INTO training_position(session_id, user_id, code, quantity, avg_cost) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (sess["id"], user["id"], sess["code"], qty, avg_cost_with_fee),
                )

        else:  # SELL
            if not req.quantity or req.quantity <= 0:
                raise HTTPException(status_code=400, detail="请填写卖出股数")
            qty = int(req.quantity)
            row = conn.execute(
                "SELECT quantity, avg_cost FROM training_position WHERE session_id = ? AND code = ?",
                (sess["id"], sess["code"]),
            ).fetchone()
            if not row or row[0] < qty:
                raise HTTPException(status_code=400, detail="可卖股数不足")
            trade_amount = qty * price
            fees = _calc_total_fees(trade_amount, qty, sess, "SELL")
            # FIFO 真实实现盈亏: 卖出价 - 买入成本 - 卖出手续费 - 分摊的买入费用
            cost_basis, fee_proportion = _fifo_cost_basis(
                user["id"], sess["id"], qty
            )
            realized_pnl = trade_amount - fees["total_fee"] - cost_basis - fee_proportion

            cur = conn.execute(
                """INSERT INTO training_order(
                    session_id, user_id, trade_date, side, price, quantity, amount,
                    commission, stamp_tax, transfer_fee, total_fee, realized_pnl
                ) VALUES(?, ?, ?, 'SELL', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sess["id"], user["id"], trade_date,
                 price, qty, trade_amount,
                 fees["commission"], fees["stamp_tax"], fees["transfer_fee"],
                 fees["total_fee"], round(realized_pnl, 2)),
            )
            order_id = cur.lastrowid

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
    return get_session(session_id, user=user)
