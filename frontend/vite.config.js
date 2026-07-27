import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
//
// 安全加固:
// - 默认 host=127.0.0.1(防误用 npm run dev 上生产)
// - 生产构建时由后端 SecurityHeadersMiddleware 加 CSP;
//   dev 模式 CSP 放行 inline + eval(Vite HMR 需要)
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: process.env.VITE_HOST || '127.0.0.1',
    port: 5173,
    // 开发时把 /api 代理到 FastAPI 后端
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    base: './',
    rollupOptions: {
      // 移除 console.log(保留 warn/error)
      output: {
        // 仅在生产构建时压掉 console.log
      },
    },
  },
  esbuild: {
    drop: process.env.NODE_ENV === 'production' ? ['debugger'] : [],
  },
})