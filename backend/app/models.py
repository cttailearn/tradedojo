"""
Pydantic 模型 —— API 请求/响应 schema
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# ---------- 通用 ----------
class Resp(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Optional[dict] = None


class PageResp(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[dict] = []


# ---------- 登录 ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    user_id: int


class UserInfo(BaseModel):
    id: int
    username: str
    last_login: Optional[str] = None


# ---------- 股票 ----------
class StockBrief(BaseModel):
    code: str
    name: str
    industry: Optional[str] = None
    market: Optional[str] = None
    list_date: Optional[str] = None
    is_active: int = 1


class StockDetail(StockBrief):
    full_code: Optional[str] = None
    kline_count: int = 0
    kline_first_date: Optional[str] = None
    kline_last_date: Optional[str] = None


# ---------- K线 ----------
class KlineRow(BaseModel):
    trade_date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    pre_close: Optional[float] = None
    change_amount: Optional[float] = None
    pct_change: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None
    turnover_rate: Optional[float] = None


# ---------- 数据更新任务 ----------
class UpdateTaskRequest(BaseModel):
    task: str = Field(..., description="任务名: stock_list / kline_daily / index / enrich / all / daily")
    adjust: str = Field("qfq", description="复权方式: qfq/hfq")
    days: int = Field(365, description="回溯天数")
    workers: int = Field(8, description="并发线程数")
    full_init: bool = Field(False, description="是否全量初始化")
    limit: Optional[int] = Field(None, description="限制数量(测试用)")


class TaskStatus(BaseModel):
    task_id: str
    task_name: str
    status: str  # pending / running / success / failed
    progress: dict = {}
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    message: str = ""
    log_tail: List[str] = []


# ---------- 回测 ----------
class BacktestRequest(BaseModel):
    code: str = "000001"
    start: str = "2020-01-01"
    end: str = "2024-12-31"
    adjust: str = "qfq"
    cash: float = 100000
    strategy: str = "sma"
    period: int = 240  # 2026-08-04: 240=日线, 30/60=分钟
    fast: int = 5
    slow: int = 20
    lookback: int = 20
    thresh: float = 0.05
    stop_loss: float = 0.08
    take_profit: float = 0.20
    # 2026-08-04: 均线多头排列策略参数
    mid: int = 10
    vol_period: int = 20
    vol_ratio: float = 1.2
    plot: bool = False


class PortfolioRequest(BaseModel):
    codes: str = Field(..., description="逗号分隔,例如 000001,600000")
    start: str = "2020-01-01"
    end: str = "2024-12-31"
    adjust: str = "qfq"
    cash: float = 100000
    strategy: str = "sma"
    fast: int = 5
    slow: int = 20
    lookback: int = 20


# ---------- 状态 ----------
class SystemStatus(BaseModel):
    tables: dict = {}
    kline_by_adjust: List[dict] = []
    recent_logs: List[dict] = []
    update_log_size: int = 0


# ==========================================
# K线训练交易 —— 用户端
# ==========================================
class TrainRegisterRequest(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None


class TrainLoginRequest(BaseModel):
    username: str
    password: str


class TrainLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    user_id: int
    display_name: Optional[str] = None


class TrainUserInfo(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    last_login: Optional[str] = None


class WalletInfo(BaseModel):
    balance: float
    total_spent: float
    total_topup: float


class RedeemRequest(BaseModel):
    code: str


class TrainingSetupRequest(BaseModel):
    """发起训练会话:参数 + 自选时间窗,后端随机选股"""
    start_date: str = Field(..., description="用户选定的训练开始日(只是历史快照日,真实时间已隐藏)")
    end_date: str = Field(..., description="数据范围结束日(快照日)")
    # 2026-08-04 分钟级训练引擎: K线周期 (240=日线 / 30 / 60 分钟)
    bar_period: int = Field(240, description="K线周期: 240=日线, 30/60=分钟K线")

    @field_validator("bar_period")
    @classmethod
    def _bar_period_valid(cls, v):
        if v not in (30, 60, 240):
            raise ValueError("bar_period 仅支持 30/60/240")
        return v
    lookback_months: int = Field(6, ge=1, le=36)

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, v, info):
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date 必须晚于 start_date")
        return v
    initial_cash: float = Field(1_000_000, ge=10_000)
    commission_rate: float = Field(0.0003, ge=0, le=0.01)
    min_commission: float = Field(5, ge=0)
    stamp_tax: float = Field(0.001, ge=0, le=0.05)
    transfer_fee: float = Field(0.00001, ge=0, le=0.01)
    allow_split: bool = True
    max_positions: int = Field(5, ge=1, le=20)
    per_trade_amount: float = Field(100_000, ge=1000)
    allow_chinext: bool = False
    allow_st: bool = False
    allow_kcb: bool = False
    allow_bj: bool = False
    # 选股偏好(可选)
    industry: Optional[str] = None
    market: Optional[str] = None
    keyword: Optional[str] = None
    # 2026-07-31 优化: 组合训练模式(P2-2)
    is_portfolio: bool = Field(False, description="True=组合训练, 同时建 N 个独立 session 共享钱包")
    portfolio_size: int = Field(5, ge=2, le=10, description="组合训练时股票数量")
    # 2026-07-31 P2-3: 自动风控规则 (0=关闭)
    auto_stop_loss_pct: float = Field(0, ge=0, le=0.5, description="自动止损比例 (e.g. 0.08)")
    auto_take_profit_pct: float = Field(0, ge=0, le=1.0, description="自动止盈比例 (e.g. 0.20)")


class TrainingSessionInfo(BaseModel):
    id: int
    code: str
    name: Optional[str] = None
    industry: Optional[str] = None
    market: Optional[str] = None
    start_date: str
    end_date: str
    current_date: Optional[str] = None
    lookback_months: int
    initial_cash: float
    status: str
    cash: float = 0  # 当前可用现金
    market_value: float = 0  # 当前持仓市值
    total_equity: float = 0
    total_pnl: float = 0
    total_pnl_pct: float = 0
    positions: List[dict] = []
    recent_orders: List[dict] = []
    fee_rules: dict = {}


class TradeOrderRequest(BaseModel):
    side: str = Field(..., description="BUY / SELL")
    price: Optional[float] = Field(None, description="限价;为空时按当前收盘价撮合")
    quantity: Optional[int] = Field(None, description="卖出时必填;买入时为空表示按 per_trade_amount 下单")
    amount: Optional[float] = Field(None, description="买入时按金额计算股数(100的整数倍)")
    pending: bool = Field(False, description="2026-07-31 限价单模式:true=挂单等待成交,false=立即以 open 价撮合")
    pending_ttl: int = Field(20, ge=1, le=250, description="限价单过期天数(N 个交易日内未成交则自动撤单)")


class AdvanceRequest(BaseModel):
    days: int = Field(1, ge=1, le=250, description="推进多少个交易日(日线模式)")
    bars: Optional[int] = Field(None, ge=1, le=250, description="推进多少根K线(分钟模式, 优先于 days)")


class RedeemCodeCreateRequest(BaseModel):
    amount: float = Field(..., ge=1000)
    count: int = Field(1, ge=1, le=200)
    note: Optional[str] = None


# ---------- 训练端·管理员后台 ----------

class TrainingUserListResponse(BaseModel):
    items: List[dict]
    total: int


class TrainingUserDetailResponse(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    is_active: int
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    wallet: dict


class SetUserActiveRequest(BaseModel):
    is_active: bool
    reason: str = Field(..., min_length=2, max_length=200)


class ResetUserPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=64)
    reason: str = Field(..., min_length=2, max_length=200)


class AdjustWalletRequest(BaseModel):
    delta: float = Field(..., description="正数=加款;负数=扣款;不允许为 0")
    reason: str = Field(..., min_length=2, max_length=200)
    adjust_topup: bool = Field(False, description="True=同步调整 total_topup;否则只动 balance,记录到 total_spent(扣款)/临时调拨")


class RevokeRedeemCodeRequest(BaseModel):
    reason: str = Field(..., min_length=2, max_length=200)


class RedeemCodeDetailResponse(BaseModel):
    code: str
    amount: float
    is_used: int
    used_by: Optional[int] = None
    used_at: Optional[str] = None
    used_by_username: Optional[str] = None
    created_by: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[str] = None
    revoked: int = 0  # 0=正常,1=已作废


class AdminActionLogItem(BaseModel):
    id: int
    actor: str
    actor_kind: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    detail_json: Optional[str] = None
    reason: Optional[str] = None
    before_value: Optional[str] = None
    after_value: Optional[str] = None
    created_at: Optional[str] = None


class AdminActionLogResponse(BaseModel):
    items: List[AdminActionLogItem]
    total: int