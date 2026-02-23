import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/sds/web/',
  server: { proxy: { '/auth': 'http://localhost:8201', '/sds': 'http://localhost:8201' } },
})
