"""
K线交易训练 —— 业务主路由
- 随机选股 / 开训练场
- 时间推进(逐日揭示 K 线)
- 下单撮合(买入/卖出)
- 持仓 / 资金 / 成交记录
"""
import random
import sqlite3
import math
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps_train import get_current_train_user
from app.models import (
    AdvanceRequest,
    TradeOrderRequest,
    TrainingSessionInfo,
    TrainingSetupRequest,
)
from db.database import execute, get_conn, query_all, query_one


router = APIRouter(prefix="/api/train", tags=["训练端-交易"],
                   dependencies=[Depends(get_current_train_user)])


# =========================================================
# Helpers
# =========================================================
def _pick_random_stock(req: TrainingSetupRequest) -> dict:
    """根据训练参数随机挑一只符合过滤条件的股票"""
    # 注意:同时关联 stock_list 和 kline_daily,两表都有 code 列,
    # 所以所有过滤条件都要用 s.code / s.market / s.industry 限定前缀
    where = ["s.is_active = 1"]
    params = []

    if not req.allow_chinext:
        # 创业板:深圳 30xxxx
        where.append("s.code NOT LIKE '30%'")
    if not req.allow_kcb:
        # 科创板:上海 688xxx
        where.append("s.code NOT LIKE '688%'")
    if not req.allow_bj:
        # 北交所:8xxxxx, 92xxxx, 4xxxxx(老三板), 83xxxx 等
        where.append("s.code NOT LIKE '8%' AND s.code NOT LIKE '92%'")
    # A股主板/中小板:600/601/603/000/002

    if req.market:
        where.append("s.market = ?")
        params.append(req.market)
    if req.industry:
        where.append("s.industry = ?")
        params.append(req.industry)
    if req.keyword:
        where.append("(s.code LIKE ? OR s.name LIKE ?)")
        kw = f"%{req.keyword}%"
        params.extend([kw, kw])

    # 要求该股有足够的历史K线(>= lookback_months * 20 根)
    # 通过子查询过滤
    sql = f"""
        SELECT s.code, s.name, s.industry, s.market, COUNT(k.trade_date) AS kcnt,
               MIN(k.trade_date) AS first_dt, MAX(k.trade_date) AS last_dt
        FROM stock_list s
        JOIN kline_daily k
          ON k.code = s.code AND k.adjust_type = 'qfq'
        WHERE {' AND '.join(where)}
        GROUP BY s.code, s.name, s.industry, s.market
        HAVING COUNT(k.trade_date) >= ?
           AND MIN(k.trade_date) <= ?
           AND MAX(k.trade_date) >= ?
        ORDER BY RANDOM()
        LIMIT 1
    """
    min_bars = req.lookback_months * 20
    # 给一个宽松的上限结束
    row = query_one(sql, params + [min_bars, req.start_date, req.end_date])
    if not row:
        # 退一步:不限 K 线数,只要至少有一根
        sql2 = f"""
            SELECT s.code, s.name, s.industry, s.market,
                   MIN(k.trade_date), MAX(k.trade_date)
            FROM stock_list s
            LEFT JOIN kline_daily k
              ON k.code = s.code AND k.adjust_type = 'qfq'
            WHERE {' AND '.join(where)}
            GROUP BY s.code, s.name, s.industry, s.market
            HAVING MAX(k.trade_date) IS NOT NULL
               AND MAX(k.trade_date) >= ?
            ORDER BY RANDOM()
            LIMIT 1
        """
        row = query_one(sql2, params + [req.start_date])
        if not row:
            raise HTTPException(status_code=404, detail="没有符合条件的股票(请放宽过滤或检查 K 线数据)")

    code, name, industry, market = row[0], row[1], row[2], row[3]
    # ST 过滤(只能事后判断): 检查名称
    if not req.allow_st and name and ("ST" in name.upper() or "*ST" in name):
        # 重抽一次,最多 5 次
        for _ in range(5):
            row = query_one(sql, params + [min_bars, req.start_date, req.end_date])
            if row and (not row[1] or "ST" not in row[1].upper()):
                return {"code": row[0], "name": row[1], "industry": row[2], "market": row[3]}
        # 实在找不到就保留第一个
    return {"code": code, "name": name, "industry": industry, "market": market}


def _kline_in_window(code: str, start_date: str, end_date: str) -> list:
    """读取某只股票在 [start, end] 区间的 K 线"""
    rows = query_all(
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


def _realized_pnl_for_buy(user_id: int, session_id: int, sell_qty: int) -> tuple[float, float]:
    """FIFO 计算本次卖出对应的成本(按所有 BUY 订单);返回 (cost_basis)"""
    rows = query_all(
        "SELECT id, quantity, price, commission FROM training_order "
        "WHERE user_id = ? AND session_id = ? AND side = 'BUY' "
        "ORDER BY trade_date ASC, id ASC",
        (user_id, session_id),
    )
    cost = 0.0
    remaining = sell_qty
    for _id, qty, price, fee in rows:
        if remaining <= 0:
            break
        take = min(qty, remaining)
        cost += take * price + (fee or 0) * take / max(qty, 1)
        remaining -= take
    return cost, 0.0


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
def start_session(req: TrainingSetupRequest, user: dict = Depends(get_current_train_user)):
    """发起一场训练:消费钱包余额、随机选股、写入 session"""
    # 1. 计算本次会话需消耗的训练资金(按 initial_cash 的 1% 起步, 越大约便宜, 上限 50 元)
    session_cost = min(max(req.initial_cash * 0.01, 5), 50)

    with get_conn() as conn:
        # 扣费 + 选股(事务)
        cur = conn.execute(
            "SELECT balance FROM training_wallet WHERE user_id = ?",
            (user["id"],),
        ).fetchone()
        balance = float(cur[0] or 0) if cur else 0.0
        if balance < session_cost:
            raise HTTPException(status_code=402, detail=f"训练资金不足,本次需要 {session_cost:.2f} 元")
        conn.execute(
            "UPDATE training_wallet SET balance = balance - ?, "
            "total_spent = total_spent + ?, "
            "updated_at = datetime('now', 'localtime') WHERE user_id = ?",
            (session_cost, session_cost, user["id"]),
        )

        # 随机选股
        req_sub = TrainingSetupRequest(**req.model_dump())
        stock = _pick_random_stock(req_sub)

        # 初始揭示 = 训练开始日,从这一天起,用户能向前看 lookback 月数的历史数据,
        # 但 K 线只能往后逐日推进:所以我们把 current_date 设置为 start_date 当天
        # (用户立刻能看到 start_date 之前的全部历史 K 线作为分析依据)
        current_dt = req.start_date

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
    view["wallet_balance_after"] = balance - session_cost
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
def advance(session_id: int, req: AdvanceRequest, user: dict = Depends(get_current_train_user)):
    """时间推进:把 current_date 向后推 N 个交易日;返回新的视图"""
    sess = _session_for_user(user["id"], session_id)
    if sess["status"] != "active":
        raise HTTPException(status_code=400, detail="该训练已结束")

    # 找接下来 N 个交易日 (<= end_date)
    rows = query_all(
        "SELECT trade_date FROM kline_daily "
        "WHERE code = ? AND adjust_type = 'qfq' AND trade_date > ? AND trade_date <= ? "
        "ORDER BY trade_date ASC LIMIT ?",
        (sess["code"], sess["reveal_date"], sess["end_date"], req.days),
    )
    if not rows:
        raise HTTPException(status_code=400, detail="已到达训练终点")
    new_current = rows[-1][0]

    execute(
        "UPDATE training_session SET reveal_date = ?, updated_at = datetime('now','localtime') "
        "WHERE id = ?",
        (new_current, sess["id"]),
    )
    # 在每个揭示日记录权益快照(用 session 维度估算)
    # 简化:只记最后一天
    cash_eq = query_one(
        "SELECT COALESCE(cash,0) FROM training_equity WHERE session_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (sess["id"],),
    )
    # 现金来自订单推断
    paid_buy = query_one(
        "SELECT COALESCE(SUM(amount+total_fee),0) FROM training_order WHERE session_id = ? AND side = 'BUY'",
        (sess["id"],),
    )[0] or 0
    recv_sell = query_one(
        "SELECT COALESCE(SUM(amount-total_fee),0) FROM training_order WHERE session_id = ? AND side = 'SELL'",
        (sess["id"],),
    )[0] or 0
    cash = sess["initial_cash"] - paid_buy + recv_sell
    # 持仓市值
    pos_rows = query_all(
        "SELECT p.quantity, p.avg_cost, k.close "
        "FROM training_position p LEFT JOIN kline_daily k "
        "  ON k.code = p.code AND k.adjust_type = 'qfq' AND k.trade_date = ? "
        "WHERE p.session_id = ?",
        (new_current, sess["id"]),
    )
    mv = 0.0
    for qty, avg_cost, price in pos_rows:
        px = price if price is not None else (avg_cost or 0)
        mv += qty * px
    execute(
        "INSERT INTO training_equity(session_id, trade_date, cash, market_value, total_equity) "
        "VALUES(?, ?, ?, ?, ?)",
        (sess["id"], new_current, cash, mv, cash + mv),
    )

    return get_session(session_id, user=user)


@router.get("/sessions/{session_id}/kline")
def session_kline(session_id: int, period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
                  user: dict = Depends(get_current_train_user)):
    """返回已揭示的日/周/月 K 线"""
    sess = _session_for_user(user["id"], session_id)
    daily = _kline_in_window(sess["code"], sess["start_date"], sess["reveal_date"] or sess["start_date"])
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
def trade(session_id: int, req: TradeOrderRequest, user: dict = Depends(get_current_train_user)):
    """下单:买入/卖出 — 限价撮合(简单地按当前 bar close 撮合)"""
    sess = _session_for_user(user["id"], session_id)
    if sess["status"] != "active":
        raise HTTPException(status_code=400, detail="该训练已结束")
    side = req.side.upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side 必须是 BUY/SELL")

    current_dt = sess["reveal_date"] or sess["start_date"]
    bar = query_one(
        "SELECT open, high, low, close FROM kline_daily "
        "WHERE code = ? AND adjust_type = 'qfq' AND trade_date = ?",
        (sess["code"], current_dt),
    )
    if not bar:
        raise HTTPException(status_code=400, detail="当前还未揭示 K 线")

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
                (sess["id"], user["id"], current_dt,
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
            cost_basis = (row[1] or 0) * qty
            realized_pnl = trade_amount - fees["total_fee"] - cost_basis

            cur = conn.execute(
                """INSERT INTO training_order(
                    session_id, user_id, trade_date, side, price, quantity, amount,
                    commission, stamp_tax, transfer_fee, total_fee, realized_pnl
                ) VALUES(?, ?, ?, 'SELL', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sess["id"], user["id"], current_dt,
                 price, qty, trade_amount,
                 fees["commission"], fees["stamp_tax"], fees["transfer_fee"],
                 fees["total_fee"], realized_pnl),
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
    execute(
        "UPDATE training_session SET status='finished', updated_at=datetime('now','localtime') "
        "WHERE id = ? AND user_id = ?",
        (session_id, user["id"]),
    )
    return get_session(session_id, user=user)
