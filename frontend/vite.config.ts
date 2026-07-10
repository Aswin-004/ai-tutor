import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/auth': 'http://localhost:8000',
      '/chat': 'http://localhost:8000',
      '/quiz': 'http://localhost:8000',
      '/roadmap': 'http://localhost:8000',
      '/generate_roadmap': 'http://localhost:8000',
      '/documents': 'http://localhost:8000',
      '/upload_pdf': 'http://localhost:8000',
      '/user': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/feedback': 'http://localhost:8000',
      '/analytics': 'http://localhost:8000',
      '/subjects': 'http://localhost:8000',
      '/stats': 'http://localhost:8000',
      '/heartbeat': 'http://localhost:8000',
      '/voice': 'http://localhost:8000',
    },
  },
})
