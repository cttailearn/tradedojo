-- ==========================================
-- A股数据采集系统 - SQLite Schema
-- ==========================================

-- 1. 股票基础信息表
CREATE TABLE IF NOT EXISTS stock_list (
    code           TEXT PRIMARY KEY,         -- 股票代码(如 600000)
    name           TEXT,                     -- 股票名称
    full_code      TEXT,                     -- 带市场前缀(sh600000)
    industry       TEXT,                     -- 所属行业
    market         TEXT,                     -- 交易所(SH/SZ/BJ)
    list_date      TEXT,                     -- 上市日期
    is_active      INTEGER DEFAULT 1,        -- 是否在市
    updated_at     TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_stock_list_market ON stock_list(market);
CREATE INDEX IF NOT EXISTS idx_stock_list_active ON stock_list(is_active);

-- 2. 日K线表(主键: code + trade_date + adjust_type)
CREATE TABLE IF NOT EXISTS kline_daily (
    code           TEXT NOT NULL,
    trade_date     TEXT NOT NULL,            -- YYYY-MM-DD
    open           REAL,
    high           REAL,
    low            REAL,
    close          REAL,
    pre_close      REAL,
    change_amount  REAL,                     -- 涨跌额
    pct_change     REAL,                     -- 涨跌幅(%)
    volume         INTEGER,                  -- 成交量(手)
    amount         REAL,                     -- 成交额(元)
    turnover_rate  REAL,                     -- 换手率(%)
    adjust_type    TEXT DEFAULT 'qfq',       -- qfq/hfq/none
    updated_at     TEXT DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (code, trade_date, adjust_type)
);
CREATE INDEX IF NOT EXISTS idx_kline_daily_date ON kline_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_kline_daily_code ON kline_daily(code);

-- 3. 分钟K线表
CREATE TABLE IF NOT EXISTS kline_minute (
    code           TEXT NOT NULL,
    trade_time     TEXT NOT NULL,            -- YYYY-MM-DD HH:MM:SS
    period         INTEGER NOT NULL,         -- 1/5/15/30/60
    open           REAL,
    high           REAL,
    low            REAL,
    close          REAL,
    volume         INTEGER,
    amount         REAL,
    updated_at     TEXT DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (code, trade_time, period)
);
CREATE INDEX IF NOT EXISTS idx_kline_minute_code ON kline_minute(code);
CREATE INDEX IF NOT EXISTS idx_kline_minute_time ON kline_minute(trade_time);

-- 4. 指数日线
CREATE TABLE IF NOT EXISTS index_daily (
    code           TEXT NOT NULL,            -- sh000001 等
    name           TEXT,
    trade_date     TEXT NOT NULL,
    open           REAL,
    high           REAL,
    low            REAL,
    close          REAL,
    volume         INTEGER,
    amount         REAL,
    pct_change     REAL,
    PRIMARY KEY (code, trade_date)
);

-- 5. 任务执行日志
CREATE TABLE IF NOT EXISTS update_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name      TEXT NOT NULL,
    status         TEXT,                     -- success/failed/running
    affected_rows  INTEGER DEFAULT 0,
    start_time     TEXT,
    end_time       TEXT,
    message        TEXT
);
CREATE INDEX IF NOT EXISTS idx_log_task ON update_log(task_name);
CREATE INDEX IF NOT EXISTS idx_log_time ON update_log(start_time);

-- 6. 断点续传表(动态创建,见 checkpoint.py)
-- CREATE TABLE IF NOT EXISTS checkpoint_xxx (...);

-- ==========================================
-- 训练交易系统表(独立于管理端,共用同一份股票数据)
-- ==========================================

-- 训练用户账户(独立账号体系,与管理后台 admin_user 分开)
CREATE TABLE IF NOT EXISTS training_user (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    display_name  TEXT,
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now', 'localtime')),
    last_login    TEXT
);
CREATE INDEX IF NOT EXISTS idx_training_user_name ON training_user(username);

-- 用户钱包(训练资金,可消耗,用兑换码充值)
CREATE TABLE IF NOT EXISTS training_wallet (
    user_id        INTEGER PRIMARY KEY,
    balance        REAL DEFAULT 0,
    total_spent    REAL DEFAULT 0,
    total_topup    REAL DEFAULT 0,
    updated_at     TEXT DEFAULT (datetime('now', 'localtime'))
);

-- 兑换码(管理员下发或自注册,一次性使用,绑定金额)
CREATE TABLE IF NOT EXISTS redeem_code (
    code            TEXT PRIMARY KEY,
    amount          REAL NOT NULL,
    is_used         INTEGER DEFAULT 0,
    used_by         INTEGER,
    used_at         TEXT,
    created_by      TEXT,
    note            TEXT,
    revoked         INTEGER DEFAULT 0,           -- 1=管理员已作废(未使用的码)
    created_at      TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_redeem_used ON redeem_code(is_used);
-- 老库兼容:revoked 列由 db/database.init_db 中的 ensure_col ALTER 添加

-- 训练会话(每次开始训练为 1 条;锁仓参数 + 时间范围 + 选定股票)
CREATE TABLE IF NOT EXISTS training_session (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    code            TEXT NOT NULL,                  -- 股票代码
    name            TEXT,                           -- 股票名称(快照)
    industry        TEXT,
    market          TEXT,
    start_date      TEXT NOT NULL,                  -- 用户选定的训练开始日(K线上 cutoff,只能看 < 此日 的数据)
    end_date        TEXT NOT NULL,                  -- 数据范围结束日(快照)
    lookback_months INTEGER DEFAULT 6,               -- 用于回看的历史数据月数
    initial_cash    REAL DEFAULT 1000000,           -- 初始资金(快照)
    commission_rate REAL DEFAULT 0.0003,            -- 手续费率
    min_commission  REAL DEFAULT 5,                 -- 最低手续费
    stamp_tax       REAL DEFAULT 0.001,             -- 印花税(卖出)
    transfer_fee    REAL DEFAULT 0.00001,           -- 过户费
    allow_split     INTEGER DEFAULT 1,             -- 是否允许分仓
    max_positions   INTEGER DEFAULT 5,             -- 最多持仓数量
    per_trade_amount REAL DEFAULT 100000,           -- 每次下单金额
    allow_chinext   INTEGER DEFAULT 0,             -- 是否允许创业板
    allow_st        INTEGER DEFAULT 0,             -- 是否允许 ST 股
    allow_kcb       INTEGER DEFAULT 0,             -- 是否允许科创板
    allow_bj        INTEGER DEFAULT 0,             -- 是否允许北交所
    total_fee_paid  REAL DEFAULT 0,                 -- 本次会话消耗的训练资金
    status          TEXT DEFAULT 'active',          -- active / finished
    reveal_date     TEXT,                           -- 已揭示到的日期 (粘性推进)
    created_at      TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_session_user ON training_session(user_id);
CREATE INDEX IF NOT EXISTS idx_session_status ON training_session(status);

-- 训练订单(每次买入/卖出)
CREATE TABLE IF NOT EXISTS training_order (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    trade_date      TEXT NOT NULL,                  -- 撮合交易日(=当时的 current_date)
    side            TEXT NOT NULL,                  -- BUY / SELL
    price           REAL NOT NULL,
    quantity        INTEGER NOT NULL,
    amount          REAL NOT NULL,
    commission      REAL DEFAULT 0,
    stamp_tax       REAL DEFAULT 0,
    transfer_fee    REAL DEFAULT 0,
    total_fee       REAL DEFAULT 0,
    realized_pnl    REAL DEFAULT 0,                 -- 卖出时累计盈亏
    note            TEXT,
    created_at      TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_order_session ON training_order(session_id);
CREATE INDEX IF NOT EXISTS idx_order_user_date ON training_order(user_id, trade_date);

-- 训练当前持仓(每个 (session, code) 一行,数量+均价)
CREATE TABLE IF NOT EXISTS training_position (
    session_id      INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    code            TEXT NOT NULL,
    quantity        INTEGER DEFAULT 0,
    avg_cost        REAL DEFAULT 0,
    updated_at      TEXT DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (session_id, code)
);
CREATE INDEX IF NOT EXISTS idx_position_user ON training_position(user_id);
CREATE INDEX IF NOT EXISTS idx_position_user_code ON training_position(user_id, code);

-- 账户"权益曲线"快照,便于复盘 + 资金盈亏曲线
CREATE TABLE IF NOT EXISTS training_equity (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    trade_date      TEXT NOT NULL,
    cash            REAL NOT NULL,
    market_value    REAL NOT NULL,
    total_equity    REAL NOT NULL,
    created_at      TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_equity_session ON training_equity(session_id, trade_date);

-- 管理员操作日志(所有训练端 /api/train/admin/* 的写操作都进这张表,便于审计 / 追责)
CREATE TABLE IF NOT EXISTS admin_action_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    actor           TEXT NOT NULL,                   -- 操作者(用户名,目前固定为 admin)
    actor_kind      TEXT DEFAULT 'admin',            -- admin / system (留扩展)
    action          TEXT NOT NULL,                   -- 动作: create_redeem_codes / revoke_redeem_code / set_user_active /
                                                    -- reset_user_password / adjust_wallet / refund_used_code / delete_session ...
    target_type     TEXT,                            -- user / redeem_code / session
    target_id       TEXT,                            -- 目标主键的字符串形式(uid / 兑换码 / session_id)
    detail_json     TEXT,                            -- 详情(JSON 字符串,详情会因动作而异)
    reason          TEXT,                            -- 必填的调整原因
    before_value    TEXT,                            -- 动作前的关键值(如 balance)
    after_value     TEXT,                            -- 动作后的关键值
    ip              TEXT,                            -- 请求 IP(留扩展,可选)
    created_at      TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_action_log_actor ON admin_action_log(actor, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_log_target ON admin_action_log(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_action_log_action ON admin_action_log(action);
CREATE INDEX IF NOT EXISTS idx_action_log_created ON admin_action_log(created_at DESC);
