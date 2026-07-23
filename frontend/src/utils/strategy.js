/**
 * 策略模板与工具函数
 */

// 内置策略模板
export const BUILTIN_STRATEGIES = [
  {
    id: 'builtin_sma',
    name: 'SMA 双均线交叉',
    description: '当快线上穿慢线时买入，下穿时卖出。经典趋势跟踪策略。',
    type: 'sma',
    builtin: true,
    params: [
      { key: 'fast', label: '快线周期', type: 'number', default: 5, min: 2, max: 60 },
      { key: 'slow', label: '慢线周期', type: 'number', default: 20, min: 5, max: 250 },
    ],
  },
  {
    id: 'builtin_momentum',
    name: '动量突破策略',
    description: '当价格突破过去N日动量阈值时买入，设置止损止盈保护。',
    type: 'momentum',
    builtin: true,
    params: [
      { key: 'lookback', label: '回看期(天)', type: 'number', default: 20, min: 5, max: 120 },
      { key: 'thresh', label: '动量阈值', type: 'number', default: 0.05, min: 0.01, max: 0.5, step: 0.01 },
      { key: 'stop_loss', label: '止损比例', type: 'number', default: 0.08, min: 0.01, max: 0.5, step: 0.01 },
      { key: 'take_profit', label: '止盈比例', type: 'number', default: 0.20, min: 0.05, max: 1.0, step: 0.05 },
    ],
  },
  {
    id: 'builtin_buyhold',
    name: '买入持有',
    description: '在起始日全仓买入，一直持有到结束日卖出。基准策略，用于对比。',
    type: 'buy_hold',
    builtin: true,
    params: [],
  },
  {
    id: 'builtin_meanrev',
    name: '均值回归策略',
    description: '当价格低于均线一定比例时买入，回归均线时卖出。适合震荡市场。',
    type: 'custom',
    builtin: true,
    params: [
      { key: 'period', label: '均线周期', type: 'number', default: 20, min: 5, max: 120 },
      { key: 'entry_discount', label: '入场折价(%)', type: 'number', default: 5, min: 1, max: 20, step: 0.5 },
      { key: 'exit_premium', label: '离场溢价(%)', type: 'number', default: 2, min: 0, max: 10, step: 0.5 },
      { key: 'stop_loss', label: '止损(%)', type: 'number', default: 10, min: 1, max: 30, step: 0.5 },
    ],
  },
  {
    id: 'builtin_breakout',
    name: '通道突破策略',
    description: '价格突破N日最高点时买入，跌破N日最低点时卖出。适合趋势市场。',
    type: 'custom',
    builtin: true,
    params: [
      { key: 'channel_period', label: '通道周期(天)', type: 'number', default: 20, min: 5, max: 120 },
      { key: 'atr_period', label: 'ATR 周期', type: 'number', default: 14, min: 5, max: 60 },
      { key: 'atr_mult', label: 'ATR 止损倍数', type: 'number', default: 2, min: 1, max: 5, step: 0.5 },
      { key: 'position_pct', label: '仓位比例(%)', type: 'number', default: 50, min: 10, max: 100, step: 10 },
    ],
  },
]

// localStorage key
const STORAGE_KEY = 'tradedojo_strategies'

// 加载用户自定义策略
export function loadStrategies() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

// 保存用户自定义策略
export function saveStrategies(strategies) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(strategies))
}

// 生成唯一 ID
export function generateId() {
  return 'stg_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8)
}

// 生成分享码
export function encodeShareCode(strategy) {
  const data = JSON.stringify({
    n: strategy.name,
    d: strategy.description,
    t: strategy.type,
    p: strategy.params,
  })
  const encoded = btoa(unescape(encodeURIComponent(data)))
  return 'TDJ:' + encoded
}

// 解码分享码
export function decodeShareCode(code) {
  try {
    if (!code || !code.startsWith('TDJ:')) return null
    const json = decodeURIComponent(escape(atob(code.slice(4))))
    const raw = JSON.parse(json)
    return {
      id: generateId(),
      name: raw.n || '导入策略',
      description: raw.d || '',
      type: raw.t || 'custom',
      builtin: false,
      params: raw.p || [],
      createdAt: new Date().toISOString().slice(0, 10),
      updatedAt: new Date().toISOString().slice(0, 10),
    }
  } catch {
    return null
  }
}

// 根据策略类型生成回测参数
export function strategyToBacktestParams(strategy) {
  const params = {}
  for (const p of strategy.params || []) {
    params[p.key] = p.default
  }
  return {
    strategy: strategy.type === 'buy_hold' ? 'buy_hold' : (strategy.type === 'momentum' ? 'momentum' : 'sma'),
    ...params,
  }
}
