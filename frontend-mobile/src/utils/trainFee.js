/**
 * 训练费计算 - 与后端 app/utils.calc_session_cost 严格一致.
 * 修改两边必须同步!CI 会跑 parity test.
 */
export function calcSessionCost(startDate, endDate, initialCash) {
  let spanDays = 30
  try {
    if (startDate && endDate) {
      const sd = new Date(startDate)
      const ed = new Date(endDate)
      const diff = Math.round((ed.getTime() - sd.getTime()) / 86400000)
      spanDays = Math.max(1, isFinite(diff) ? diff : 30)
    }
  } catch {
    spanDays = 30
  }
  const cash = Math.min(60, (Number(initialCash) / 1_000_000) * 20)
  const v = 5 + spanDays * 0.05 + cash
  const cost = Math.max(5, Math.min(80, v))
  return Math.round(cost * 100) / 100
}

/**
 * 通用金额格式化 ¥ 1,234.56
 */
export function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/**
 * 浮点价格 → "12.34"
 */
export function price(v, digits = 2) {
  return Number(v || 0).toFixed(digits)
}

/**
 * 百分比 → "+1.23%"
 */
export function pct(v, digits = 2) {
  const n = Number(v || 0)
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(digits)}%`
}
