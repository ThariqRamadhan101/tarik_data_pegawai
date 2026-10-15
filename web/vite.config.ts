import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Relative base so the built app works from any static host / subfolder.
// /api di-proxy ke server Python (server/server.py) selama dev.
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
