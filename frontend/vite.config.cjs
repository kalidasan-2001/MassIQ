const { defineConfig } = require('vite')
const react = require('@vitejs/plugin-react')
const path = require('path')

// R3: @vitejs/plugin-react's Fast Refresh instrumentation expects a
// dev-server-injected preamble that never exists under Vitest/jsdom,
// which fails with "can't detect preamble" the moment any component is
// rendered in a test. Fast Refresh is a dev-only convenience anyway, so
// it's skipped entirely when running under Vitest (process.env.VITEST) --
// every component already does classic `import React from 'react'`, so
// Vite's default esbuild JSX transform alone is sufficient for both the
// production build and the test run; only `npm run dev`'s HMR loses
// component-level fast refresh under Vitest, which never runs `npm run dev`.
module.exports = defineConfig({
  root: __dirname,
  plugins: process.env.VITEST ? [] : [react()],
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
  cacheDir: path.resolve(__dirname, 'node_modules/.vite'),
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.js'],
    globals: true,
    // R3.5: Vitest's default glob otherwise also collects e2e/specs/*.spec.js
    // -- Playwright's own test files, which use @playwright/test's `test`/
    // `expect` (real browser page/locator APIs), not Vitest's. Running them
    // under Vitest/jsdom fails immediately since none of those APIs exist
    // there. E2E specs run exclusively via `npm run test:e2e` (Playwright).
    exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**']
  }
})
