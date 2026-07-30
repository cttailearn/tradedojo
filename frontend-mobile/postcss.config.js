/**
 * PostCSS - postcss-mobile-forever
 * 自动 px → rem 适配 (vw fallback 也可)
 * 设计稿基准 375px (iPhone SE),1rem = 100px
 */
export default {
  plugins: {
    'postcss-mobile-forever': {
      rootValue: 37.5,
      minPixelValue: 1,
      unitPrecision: 5,
      exclude: /node_modules|vant/i,
    },
    autoprefixer: {},
  },
}
