const { defineConfig } = require('vite')
const react = require('@vitejs/plugin-react')
const path = require('path')

module.exports = defineConfig({
  root: __dirname,
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: false
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: false
  },
  cacheDir: path.resolve(__dirname, 'node_modules/.vite')
})
