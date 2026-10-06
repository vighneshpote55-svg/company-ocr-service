import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  envDir: '../',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8001',
      '/ocr': 'http://localhost:8001',
      '/auth': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
    },
  },
})
