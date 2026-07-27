/**
 * 训练费计算 - 与后端 app/utils.calc_session_cost 严格一致.
 * 修改两边必须同步!CI 会跑 parity test.
 *
 * 公式:
 *   base    = 5                       元
 *   span    = max(1, end - start)     自然日
 *   cash    = min(60, cash/1e6 * 20)
 *   cost    = clamp(5 + span*0.05 + cash, 5, 80)
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
