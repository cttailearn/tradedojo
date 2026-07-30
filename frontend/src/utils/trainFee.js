/**
 * 训练费计算 - 与后端 app/utils.calc_session_cost 严格一致.
 * 修改两边必须同步!CI 会跑 parity test.
 *
 * 现为固定费用:每次发起训练扣 ¥100。
 * 与时间窗长度、初始资金均无关。
 */
export const TRAIN_SESSION_COST = 100.0

export function calcSessionCost(/* startDate, endDate, initialCash */) {
  return Math.round(TRAIN_SESSION_COST * 100) / 100
}
