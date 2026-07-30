"""
K 线交易训练 —— 交割单统计 & 行为分析

帮用户复盘自己的交易:从每笔成交中提炼出
"自己最适合的交易方式",包括:
- 胜率 / 盈亏因子 / 平均持仓天数
- 仓位偏好 / 买入价位习惯 / 行业偏好
- 持仓时长分布
- 交易风格标签 (短线客 / 长线价值 / 追涨杀跌 / 深度研究 等)
"""
from datetime import datetime
from statistics import mean, median
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, Query
from db.database import user_query_all as query_all, user_query_one as query_one
from app.deps_train import get_current_train_user

router = APIRouter(prefix="/api/train/stats", tags=["train-stats"])


# ---------- 工具:把单笔订单配对成 "完整回合"(FIFO) ----------

def _round_trips(orders: List[Dict]) -> List[Dict]:
    """
    将 orders(按 id ASC,已经按时间正序)按股票代码 FIFO 配对成 round-trip。
    同一股票的所有 BUY 累计,直到 SELL 出现;SELL 按比例冲销之前的 BUY。
    返回每个 round-trip 的:{code, name, buy_date, buy_price, sell_date, sell_price,
                              quantity, holding_days, realized_pnl, pnl_pct, session_id}
    """
    # 按 code 分桶,然后 FIFO 配对
    by_code: Dict[str, List[Dict]] = {}
    for o in orders:
        by_code.setdefault(o["code"], []).append(o)

    trips = []
    for code, lst in by_code.items():
        holding: List[Dict] = []  # [{trade_date, price, qty, session_id, name, industry}]
        for o in lst:
            if o["side"] == "BUY":
                holding.append({
                    "trade_date": o["trade_date"],
                    "price": o["price"],
                    "qty": o["quantity"],
                    "session_id": o.get("session_id"),
                    "name": o.get("name", ""),
                    "industry": o.get("industry", ""),
                })
            else:  # SELL
                qty_to_sell = o["quantity"]
                sell_price = o["price"]
                sell_date = o["trade_date"]
                # 把 realized_pnl 按比例分配到每段 BUY
                # (这里采用简化版:把每个 SELL 的 realized_pnl 平均到每一对 round-trip 上,
                #  每个 round-trip 的 realized_pnl ≈ 总 pnl × 该 round-trip 数量 / 总卖出数量)
                sell_session_id = o.get("session_id")
                while qty_to_sell > 0 and holding:
                    buy = holding[0]
                    q = min(qty_to_sell, buy["qty"])
                    pnl = (sell_price - buy["price"]) * q
                    pnl_pct = ((sell_price / buy["price"]) - 1) * 100
                    buy_d = datetime.strptime(buy["trade_date"], "%Y-%m-%d")
                    sell_d = datetime.strptime(sell_date, "%Y-%m-%d")
                    holding_days = (sell_d - buy_d).days
                    trips.append({
                        "code": code,
                        "name": buy["name"],
                        "industry": buy["industry"],
                        "session_id": buy["session_id"],
                        "buy_date": buy["trade_date"],
                        "buy_price": buy["price"],
                        "sell_date": sell_date,
                        "sell_price": sell_price,
                        "quantity": q,
                        "holding_days": holding_days,
                        "realized_pnl": pnl,
                        "pnl_pct": pnl_pct,
                    })
                    buy["qty"] -= q
                    qty_to_sell -= q
                    if buy["qty"] <= 0:
                        holding.pop(0)
    return trips


# ---------- 工具:从 kline_daily 取当日高低点,算买入价位 ----------

def _price_position_lookup(buys: List[Dict]) -> Dict[int, float]:
    """
    对每条 BUY 订单,用当日的 (high, low) 算
    price_position = (price - low) / (high - low) ∈ [0, 1]
    返回 {order_id: position}
    """
    if not buys:
        return {}
    out = {}
    for o in buys:
        row = query_one(
            "SELECT high, low FROM kline_daily "
            "WHERE code = ? AND adjust_type = 'qfq' AND trade_date = ?",
            (o["code"], o["trade_date"]),
        )
        if not row:
            continue
        hi, lo = row[0], row[1]
        if hi is None or lo is None or hi <= lo:
            out[o["id"]] = 0.5
        else:
            pos = (o["price"] - lo) / (hi - lo)
            out[o["id"]] = max(0.0, min(1.0, pos))
    return out


# ---------- 主端点:综合统计 ----------

@router.get("/overview")
def overview(user: dict = Depends(get_current_train_user)):
    """
    用户训练数据全景:
    - 基础面板
    - 持仓时长分布
    - 仓位偏好
    - 买入价位习惯
    - 行业/股票偏好
    - 交易风格标签
    """
    user_id = user["id"]

    # 1. 拉取该用户所有 session 列表
    sessions = query_all(
        "SELECT id, code, name, industry, market, status, initial_cash, "
        "       start_date, end_date, total_fee_paid, reveal_date, created_at "
        "FROM training_session WHERE user_id = ? ORDER BY id ASC",
        (user_id,),
    )
    sess_map = {}
    for s in sessions:
        sess_map[s[0]] = {
            "id": s[0], "code": s[1], "name": s[2], "industry": s[3],
            "market": s[4], "status": s[5], "initial_cash": s[6],
            "start_date": s[7], "end_date": s[8], "total_fee_paid": s[9],
            "reveal_date": s[10], "created_at": s[11],
        }

    # 2. 拉取该用户所有订单
    raw_orders = query_all(
        "SELECT o.id, o.session_id, o.trade_date, o.side, o.price, o.quantity, "
        "       o.amount, o.commission, o.stamp_tax, o.transfer_fee, "
        "       o.total_fee, o.realized_pnl, s.code, s.name, s.industry "
        "FROM training_order o "
        "JOIN training_session s ON o.session_id = s.id "
        "WHERE o.user_id = ? ORDER BY o.id ASC",
        (user_id,),
    )
    orders = []
    buys_only = []
    for r in raw_orders:
        d = {
            "id": r[0], "session_id": r[1], "trade_date": r[2], "side": r[3],
            "price": r[4], "quantity": r[5], "amount": r[6],
            "commission": r[7], "stamp_tax": r[8], "transfer_fee": r[9],
            "total_fee": r[10], "realized_pnl": r[11],
            "code": r[12], "name": r[13], "industry": r[14],
        }
        orders.append(d)
        if r[3] == "BUY":
            buys_only.append(d)

    # 3. Round-trip 配对(FIFO),得到完整回合
    trips = _round_trips(orders)

    # 4. 基础面板
    total_buy_count = sum(1 for o in orders if o["side"] == "BUY")
    total_sell_count = sum(1 for o in orders if o["side"] == "SELL")
    total_sessions = len(sessions)
    finished_sessions = sum(1 for s in sessions if s[5] == "finished")
    total_realized = sum(t["realized_pnl"] for t in trips)
    total_fees = sum(o["total_fee"] for o in orders)
    win_trips = [t for t in trips if t["realized_pnl"] > 0]
    loss_trips = [t for t in trips if t["realized_pnl"] < 0]
    win_rate = (len(win_trips) / len(trips) * 100) if trips else 0.0
    avg_pnl = (total_realized / len(trips)) if trips else 0.0
    avg_holding = mean([t["holding_days"] for t in trips]) if trips else 0.0
    median_holding = median([t["holding_days"] for t in trips]) if trips else 0.0
    best_trade = max(trips, key=lambda x: x["realized_pnl"]) if trips else None
    worst_trade = min(trips, key=lambda x: x["realized_pnl"]) if trips else None

    avg_win = mean([t["realized_pnl"] for t in win_trips]) if win_trips else 0.0
    avg_loss = mean([t["realized_pnl"] for t in loss_trips]) if loss_trips else 0.0
    profit_factor = (
        (sum(t["realized_pnl"] for t in win_trips) /
         abs(sum(t["realized_pnl"] for t in loss_trips)))
        if loss_trips else float('inf') if win_trips else 0.0
    )
    # 最大连胜 / 连败
    max_consec_win, max_consec_loss = _max_consecutive(trips)

    # 5. 持仓时长分布
    holding_dist = {
        "T+1内": 0, "T+2~3": 0, "T+4~7": 0, "T+8~20": 0,
        "T+21~60": 0, "T+60以上": 0,
    }
    holding_pnl = {k: [] for k in holding_dist.keys()}
    for t in trips:
        bucket = (
            "T+1内" if t["holding_days"] <= 1 else
            "T+2~3" if t["holding_days"] <= 3 else
            "T+4~7" if t["holding_days"] <= 7 else
            "T+8~20" if t["holding_days"] <= 20 else
            "T+21~60" if t["holding_days"] <= 60 else
            "T+60以上"
        )
        holding_dist[bucket] += 1
        holding_pnl[bucket].append(t["realized_pnl"])
    holding_distribution = [
        {
            "bucket": k,
            "count": holding_dist[k],
            "win_rate": round(_win_rate(holding_pnl[k]) * 100, 1),
            "avg_pnl": round(mean(holding_pnl[k]), 2) if holding_pnl[k] else 0,
        }
        for k in holding_dist.keys()
    ]

    # 6. 仓位偏好(每笔 BUY 占当时可用资金的比例)
    # 简化版:把 amount / (session.initial_cash * 0.95) 作为仓位系数
    position_buckets = {
        "小额(<10%)": 0, "中等(10~30%)": 0,
        "半仓(30~60%)": 0, "重仓(60~90%)": 0, "满仓(>=90%)": 0,
    }
    position_pnl = {k: [] for k in position_buckets.keys()}
    for o in buys_only:
        sess = sess_map.get(o["session_id"])
        if not sess:
            continue
        cap = sess["initial_cash"] * 0.95
        ratio = (o["amount"] / cap) if cap else 0
        bucket = (
            "小额(<10%)" if ratio < 0.10 else
            "中等(10~30%)" if ratio < 0.30 else
            "半仓(30~60%)" if ratio < 0.60 else
            "重仓(60~90%)" if ratio < 0.90 else
            "满仓(>=90%)"
        )
        position_buckets[bucket] += 1
    # 把配对的 trip pnl 按比例归到对应 bucket (按 buy_date 找对应 trip)
    trip_by_buy_date = {(t["buy_date"], t["code"], t["quantity"]): t for t in trips}
    for o in buys_only:
        # 找该 BUY 对应的 trip (找任意匹配 buy_date+code)
        matched = None
        for t in trips:
            if t["buy_date"] == o["trade_date"] and t["code"] == o["code"]:
                matched = t
                break
        if not matched:
            continue
        sess = sess_map.get(o["session_id"])
        if not sess:
            continue
        cap = sess["initial_cash"] * 0.95
        ratio = (o["amount"] / cap) if cap else 0
        bucket = (
            "小额(<10%)" if ratio < 0.10 else
            "中等(10~30%)" if ratio < 0.30 else
            "半仓(30~60%)" if ratio < 0.60 else
            "重仓(60~90%)" if ratio < 0.90 else
            "满仓(>=90%)"
        )
        position_pnl[bucket].append(matched["realized_pnl"])
    position_distribution = [
        {
            "bucket": k,
            "count": position_buckets[k],
            "win_rate": round(_win_rate(position_pnl[k]) * 100, 1),
            "avg_pnl": round(mean(position_pnl[k]), 2) if position_pnl[k] else 0,
        }
        for k in position_buckets.keys()
    ]

    # 7. 买入价位习惯
    price_pos_map = _price_position_lookup(buys_only)
    price_pos_buckets = {
        "低吸(<33%)": [], "中段(33~66%)": [], "追高(>=66%)": [],
    }
    for o in buys_only:
        pos = price_pos_map.get(o["id"])
        if pos is None:
            continue
        # 把 BUY 的 pnl 关联到 trip
        matched_trip = None
        for t in trips:
            if t["buy_date"] == o["trade_date"] and t["code"] == o["code"]:
                matched_trip = t
                break
        pnl = matched_trip["realized_pnl"] if matched_trip else None
        bucket = (
            "低吸(<33%)" if pos < 0.33 else
            "中段(33~66%)" if pos < 0.66 else
            "追高(>=66%)"
        )
        price_pos_buckets[bucket].append((pos, pnl))
    price_position_distribution = []
    for bucket, items in price_pos_buckets.items():
        pnls = [p for _, p in items if p is not None]
        price_position_distribution.append({
            "bucket": bucket,
            "count": len(items),
            "avg_position": round(mean([p for p, _ in items]), 2) if items else 0,
            "win_rate": round(_win_rate(pnls) * 100, 1) if pnls else 0,
            "avg_pnl": round(mean(pnls), 2) if pnls else 0,
        })

    # 8. 行业偏好(按 industry 聚合)
    industry_map: Dict[str, Dict[str, Any]] = {}
    for t in trips:
        ind = t["industry"] or "未分类"
        m = industry_map.setdefault(ind, {"count": 0, "pnl": 0.0, "wins": 0})
        m["count"] += 1
        m["pnl"] += t["realized_pnl"]
        if t["realized_pnl"] > 0:
            m["wins"] += 1
    industry_ranking = sorted(
        [{
            "industry": k, "count": v["count"],
            "win_rate": round(v["wins"] / v["count"] * 100, 1),
            "total_pnl": round(v["pnl"], 2),
        } for k, v in industry_map.items()],
        key=lambda x: x["total_pnl"], reverse=True,
    )

    # 9. 股票偏好(按 code 聚合)
    stock_map: Dict[str, Dict[str, Any]] = {}
    for t in trips:
        code = t["code"]
        m = stock_map.setdefault(code, {"name": t["name"], "count": 0, "pnl": 0.0, "wins": 0})
        m["count"] += 1
        m["pnl"] += t["realized_pnl"]
        if t["realized_pnl"] > 0:
            m["wins"] += 1
    stock_ranking = sorted(
        [{
            "code": k, "name": v["name"], "count": v["count"],
            "win_rate": round(v["wins"] / v["count"] * 100, 1) if v["count"] else 0,
            "total_pnl": round(v["pnl"], 2),
        } for k, v in stock_map.items()],
        key=lambda x: x["total_pnl"], reverse=True,
    )[:10]  # top 10

    # 10. 月度盈亏
    monthly: Dict[str, float] = {}
    for t in trips:
        m = t["sell_date"][:7]
        monthly[m] = monthly.get(m, 0.0) + t["realized_pnl"]
    monthly_pnl = [{"month": k, "pnl": round(v, 2)} for k, v in sorted(monthly.items())]

    # 11. 交易风格标签
    style_tags = _derive_style_tags(
        avg_holding=avg_holding,
        median_holding=median_holding,
        total_buy_count=total_buy_count,
        total_sessions=total_sessions,
        trips=trips,
        win_rate=win_rate,
        avg_win=avg_win, avg_loss=avg_loss,
        profit_factor=profit_factor,
        position_distribution=position_distribution,
        price_position_distribution=price_position_distribution,
    )

    # 12. 会话列表 + 摘要(供前端选择查看单次训练)
    sessions_summary = []
    for s in sessions:
        # 计算该 session 的总 pnl
        s_trips = [t for t in trips if t["session_id"] == s[0]]
        s_orders = [o for o in orders if o["session_id"] == s[0]]
        sessions_summary.append({
            "id": s[0], "code": s[1], "name": s[2],
            "industry": s[3], "status": s[5],
            "trade_count": len(s_orders),
            "round_trip_count": len(s_trips),
            "total_pnl": round(sum(t["realized_pnl"] for t in s_trips), 2),
            "start_date": s[7], "end_date": s[8],
            "reveal_date": s[10],
            "created_at": s[11],
        })

    return {
        "summary": {
            "total_sessions": total_sessions,
            "finished_sessions": finished_sessions,
            "active_sessions": total_sessions - finished_sessions,
            "total_buy_count": total_buy_count,
            "total_sell_count": total_sell_count,
            "total_round_trips": len(trips),
            "win_count": len(win_trips),
            "loss_count": len(loss_trips),
            "win_rate": round(win_rate, 1),
            "total_realized_pnl": round(total_realized, 2),
            "total_fees_paid": round(total_fees, 2),
            "avg_pnl_per_trade": round(avg_pnl, 2),
            "avg_holding_days": round(avg_holding, 1),
            "median_holding_days": round(median_holding, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": (round(profit_factor, 2)
                              if isinstance(profit_factor, float)
                              and profit_factor != float('inf') else None),
            "max_consecutive_win": max_consec_win,
            "max_consecutive_loss": max_consec_loss,
            "best_trade": _safe_trip_summary(best_trade),
            "worst_trade": _safe_trip_summary(worst_trade),
        },
        "holding_distribution": holding_distribution,
        "position_distribution": position_distribution,
        "price_position_distribution": price_position_distribution,
        "industry_ranking": industry_ranking,
        "stock_ranking": stock_ranking,
        "monthly_pnl": monthly_pnl,
        "style_tags": style_tags,
        "sessions": sessions_summary,
    }


# ---------- 单 session 统计 ----------

@router.get("/session/{session_id}")
def session_stats(session_id: int, user: dict = Depends(get_current_train_user)):
    """单个训练场的详细复盘数据"""
    sess = query_one(
        "SELECT * FROM training_session WHERE id = ? AND user_id = ?",
        (session_id, user["id"]),
    )
    if not sess:
        return None
    raw_orders = query_all(
        "SELECT o.id, o.session_id, o.trade_date, o.side, o.price, o.quantity, "
        "       o.amount, o.commission, o.stamp_tax, o.transfer_fee, "
        "       o.total_fee, o.realized_pnl, s.code, s.name, s.industry "
        "FROM training_order o "
        "JOIN training_session s ON o.session_id = s.id "
        "WHERE o.session_id = ? ORDER BY o.id ASC",
        (session_id,),
    )
    orders = [{
        "id": r[0], "session_id": r[1], "trade_date": r[2], "side": r[3],
        "price": r[4], "quantity": r[5], "amount": r[6],
        "commission": r[7], "stamp_tax": r[8], "transfer_fee": r[9],
        "total_fee": r[10], "realized_pnl": r[11],
        "code": r[12], "name": r[13], "industry": r[14],
    } for r in raw_orders]
    trips = _round_trips(orders)
    buys_only = [o for o in orders if o["side"] == "BUY"]

    win_trips = [t for t in trips if t["realized_pnl"] > 0]
    loss_trips = [t for t in trips if t["realized_pnl"] < 0]
    win_rate = (len(win_trips) / len(trips) * 100) if trips else 0.0
    avg_win = mean([t["realized_pnl"] for t in win_trips]) if win_trips else 0.0
    avg_loss = mean([t["realized_pnl"] for t in loss_trips]) if loss_trips else 0.0
    avg_holding = mean([t["holding_days"] for t in trips]) if trips else 0.0

    price_pos_map = _price_position_lookup(buys_only)
    decisions = []
    for o in buys_only:
        # 找该 BUY 对应的 trip
        matched_trip = None
        for t in trips:
            if t["buy_date"] == o["trade_date"] and t["code"] == o["code"]:
                matched_trip = t
                break
        decisions.append({
            "trade_date": o["trade_date"],
            "side": "BUY",
            "code": o["code"], "name": o["name"],
            "price": o["price"], "quantity": o["quantity"],
            "amount": o["amount"], "total_fee": o["total_fee"],
            "price_position": price_pos_map.get(o["id"]),
            "matched_trip": matched_trip,
        })
    # 也把 SELL 列出来
    for o in orders:
        if o["side"] != "SELL":
            continue
        decisions.append({
            "trade_date": o["trade_date"],
            "side": "SELL",
            "code": o["code"], "name": o["name"],
            "price": o["price"], "quantity": o["quantity"],
            "amount": o["amount"], "total_fee": o["total_fee"],
            "realized_pnl": o["realized_pnl"],
        })

    decisions.sort(key=lambda x: x["trade_date"])

    return {
        "session": {
            "id": sess[0], "code": sess[2], "name": sess[3],
            "industry": sess[4], "market": sess[5],
            "status": sess[16],
            "start_date": sess[8], "end_date": sess[9],
            "initial_cash": sess[10],
            "reveal_date": sess[17],
        },
        "stats": {
            "total_buy": sum(1 for o in orders if o["side"] == "BUY"),
            "total_sell": sum(1 for o in orders if o["side"] == "SELL"),
            "round_trip_count": len(trips),
            "win_count": len(win_trips),
            "loss_count": len(loss_trips),
            "win_rate": round(win_rate, 1),
            "total_pnl": round(sum(t["realized_pnl"] for t in trips), 2),
            "total_fees": round(sum(o["total_fee"] for o in orders), 2),
            "avg_holding_days": round(avg_holding, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
        },
        "round_trips": [{
            "code": t["code"], "name": t["name"], "industry": t["industry"],
            "buy_date": t["buy_date"], "buy_price": t["buy_price"],
            "sell_date": t["sell_date"], "sell_price": t["sell_price"],
            "quantity": t["quantity"], "holding_days": t["holding_days"],
            "realized_pnl": round(t["realized_pnl"], 2),
            "pnl_pct": round(t["pnl_pct"], 2),
        } for t in trips],
        "decisions": [{
            **{k: v for k, v in d.items() if k != "matched_trip"},
            "realized_pnl": (
                round(d["matched_trip"]["realized_pnl"], 2)
                if d.get("matched_trip") else d.get("realized_pnl")
            ),
            "holding_days": (
                d["matched_trip"]["holding_days"]
                if d.get("matched_trip") else None
            ),
        } for d in decisions],
    }


# ---------- 工具函数 ----------

def _win_rate(pnls: List[float]) -> float:
    if not pnls:
        return 0.0
    return sum(1 for p in pnls if p > 0) / len(pnls)


def _max_consecutive(trips: List[Dict]) -> tuple:
    if not trips:
        return 0, 0
    max_w = max_l = cw = cl = 0
    for t in trips:
        if t["realized_pnl"] > 0:
            cw += 1; cl = 0
            max_w = max(max_w, cw)
        else:
            cl += 1; cw = 0
            max_l = max(max_l, cl)
    return max_w, max_l


def _safe_trip_summary(t: Dict | None) -> Dict | None:
    if not t:
        return None
    return {
        "code": t["code"], "name": t["name"],
        "buy_date": t["buy_date"], "sell_date": t["sell_date"],
        "quantity": t["quantity"],
        "realized_pnl": round(t["realized_pnl"], 2),
        "pnl_pct": round(t["pnl_pct"], 2),
        "holding_days": t["holding_days"],
    }


def _derive_style_tags(
    avg_holding: float, median_holding: float,
    total_buy_count: int, total_sessions: int,
    trips: List[Dict],
    win_rate: float, avg_win: float, avg_loss: float,
    profit_factor: float,
    position_distribution: List[Dict],
    price_position_distribution: List[Dict],
) -> List[Dict]:
    """基于客观指标生成 4-5 个交易风格标签,每条带描述"""
    tags = []

    # 1. 持仓周期 → 短线 / 中线 / 长线
    if avg_holding <= 3:
        tags.append({
            "tag": "短线快进快出",
            "level": "info",
            "desc": f"平均持仓 {avg_holding:.1f} 天,属于典型的短线交易风格,对手续费较为敏感。",
        })
    elif avg_holding <= 15:
        tags.append({
            "tag": "波段操作型",
            "level": "success",
            "desc": f"平均持仓 {avg_holding:.1f} 天,波段操作,关注几日内的趋势变化。",
        })
    else:
        tags.append({
            "tag": "中长期价值派",
            "level": "warning",
            "desc": f"平均持仓 {avg_holding:.1f} 天,中长期视角,适合基本面/题材跟踪。",
        })

    # 2. 交易频率
    if total_sessions > 0 and total_buy_count / total_sessions >= 10:
        tags.append({
            "tag": "高频交易者",
            "level": "danger",
            "desc": f"场均 {total_buy_count / total_sessions:.1f} 次买入,交易频率高,需警惕手续费侵蚀。",
        })
    elif total_buy_count / max(total_sessions, 1) <= 2:
        tags.append({
            "tag": "耐心等待型",
            "level": "success",
            "desc": f"场均 {total_buy_count / max(total_sessions, 1):.1f} 次买入,出手谨慎,质量优先。",
        })

    # 3. 盈亏因子
    if isinstance(profit_factor, (int, float)) and profit_factor >= 2:
        tags.append({
            "tag": "盈利能力强",
            "level": "success",
            "desc": f"盈亏因子 {profit_factor:.2f},平均盈利是平均亏损的 {profit_factor:.1f} 倍。",
        })
    elif isinstance(profit_factor, (int, float)) and profit_factor < 1 and trips:
        tags.append({
            "tag": "盈亏比偏低",
            "level": "danger",
            "desc": f"盈亏因子 {profit_factor:.2f}<1,平均亏损大于平均盈利,需要收紧止损或放宽止盈。",
        })

    # 4. 仓位偏好
    heavy = sum(
        position_distribution[i]["count"]
        for i in range(len(position_distribution))
        if position_distribution[i]["bucket"].startswith(("重仓", "满仓"))
    )
    light = sum(
        position_distribution[i]["count"]
        for i in range(len(position_distribution))
        if position_distribution[i]["bucket"].startswith("小额")
    )
    if heavy > light and heavy > 0:
        tags.append({
            "tag": "重仓出击",
            "level": "warning",
            "desc": f"重仓/满仓交易 {heavy} 次,胜率 {position_distribution[-2]['win_rate']:.0f}%,需评估是否过度暴露。",
        })
    elif light > heavy and light > 0:
        tags.append({
            "tag": "试探性建仓",
            "level": "info",
            "desc": f"以小额试探 {light} 次为主,风险敞口较小,适合震荡市。",
        })

    # 5. 买入价位习惯
    if price_position_distribution and price_position_distribution[2]["count"] > 0:
        ch_buy = price_position_distribution[2]
        if ch_buy["count"] >= 2 and ch_buy["win_rate"] < 40:
            tags.append({
                "tag": "追高倾向",
                "level": "danger",
                "desc": f"追高买入 {ch_buy['count']} 次,胜率仅 {ch_buy['win_rate']:.0f}%,建议结合分批或低吸策略。",
            })
    if price_position_distribution and price_position_distribution[0]["count"] > 0:
        low_buy = price_position_distribution[0]
        if low_buy["count"] >= 2 and low_buy["win_rate"] >= 60:
            tags.append({
                "tag": "低吸稳健",
                "level": "success",
                "desc": f"低吸买入 {low_buy['count']} 次,胜率 {low_buy['win_rate']:.0f}%,买在当日相对低点。",
            })

    # 6. 胜率总结
    if win_rate >= 60 and trips:
        tags.append({
            "tag": "胜率驱动",
            "level": "success",
            "desc": f"胜率 {win_rate:.0f}%,靠胜率累积收益,可继续保持。",
        })
    elif win_rate < 40 and trips:
        tags.append({
            "tag": "胜率偏低",
            "level": "danger",
            "desc": f"胜率 {win_rate:.0f}%,需要靠盈亏比取胜,务必设止损。",
        })

    # 至少 4 条
    if len(tags) < 4:
        tags.append({
            "tag": "数据积累中",
            "level": "info",
            "desc": "交易样本较少,继续训练以获得更准确的画像。",
        })
    return tags