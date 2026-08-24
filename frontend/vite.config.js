import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 匹配所有以 /api 开头的请求
      '/api': {
        target: 'http://127.0.0.1:8000', // 转发到你的 FastAPI 后端
        changeOrigin: true,             // 改变源，骗过后端
        secure: false,                  // 忽略证书检查
        ws: true                        // 支持 websocket / 长连接
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
})
