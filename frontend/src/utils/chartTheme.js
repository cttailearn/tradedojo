/**
 * ECharts 主题配色辅助 (2026-08-04)
 * - 根据 <html class="dark"> 返回图表配色,暗色下可读、浅色下与原有默认色一致
 * - ECharts 根 textStyle 会作为轴标签/图例等默认文本色的继承来源
 */
export function chartThemeColors() {
  const dark = document.documentElement.classList.contains('dark')
  return {
    dark,
    text: dark ? '#dbe2ee' : '#303133',          // 标题/轴标签等主要文本
    subText: dark ? '#94a3b8' : '#909399',       // 次要文本(图例/单位)
    axisLine: dark ? '#2b3c5e' : '#dcdfe6',      // 坐标轴线
    splitLine: dark ? '#1e2b45' : '#ebeef5',     // 分割线
    tooltipBg: dark ? '#0d1524' : '#ffffff',     // 提示框背景
    tooltipBorder: dark ? '#2b3c5e' : '#e4e7ed', // 提示框边框
  }
}
