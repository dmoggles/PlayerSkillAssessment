import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // The manifest tells scripts/prerender.mjs which files each prerendered page needs; the script deletes it.
  build: { manifest: true },
  server: { proxy: { '/api': { target: 'http://localhost:8000', rewrite: path => path.replace(/^\/api/, '') } } },
})
