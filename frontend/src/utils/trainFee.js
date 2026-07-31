/**
 * 训练费计算 - 与后端 app/utils.calc_session_cost 严格一致.
 * 修改两边必须同步!CI 会跑 parity test.
 *
 * 现为 0:已取消固定训练费(2026-07-31 起)。
 * 发起训练不再从余额扣任何固定费用,钱包余额全部可用于交易。
 */
export const TRAIN_SESSION_COST = 0.0

export function calcSessionCost(/* startDate, endDate, initialCash */) {
  return Math.round(TRAIN_SESSION_COST * 100) / 100
}
