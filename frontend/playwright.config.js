// R3.5 -- Playwright browser E2E configuration. See
// docs/testing/BROWSER_E2E_STRATEGY.md for the full rationale.
//
// Chromium only for now (R3.5 scope: Chromium is the required baseline;
// Firefox/WebKit are documented as future compatibility expansion, not a
// release blocker -- see the strategy doc).
//
// Runs against a fully isolated backend (its own `massiq_e2e` database,
// dropped and recreated fresh on every run; its own temp storage root) and
// a dedicated frontend dev-server port, both distinct from a developer's
// normal 8010/5173 dev servers -- see e2e/scripts/start-backend.js and the
// webServer config below. Nothing here depends on a manually-started
// server, a globally installed browser, or any machine-specific absolute
// path.
const { defineConfig, devices } = require('@playwright/test')

const FRONTEND_PORT = process.env.E2E_FRONTEND_PORT || '5190'
const BACKEND_PORT = process.env.E2E_BACKEND_PORT || '8020'
const BASE_URL = `http://127.0.0.1:${FRONTEND_PORT}`
const BACKEND_HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/health`

module.exports = defineConfig({
  testDir: './e2e/specs',
  timeout: 60 * 1000,
  expect: { timeout: 10 * 1000 },

  // Serial for this first version of the suite: the E2E backend/DB are
  // shared across the whole run (recreated once at webServer startup, not
  // per test), and each spec creates its own uniquely-named Project, which
  // makes parallel execution plausible -- but proving that out is a
  // deliberate future step, not assumed here. See "Deferred browser
  // coverage" in the R3.5 checklist.
  fullyParallel: false,
  workers: 1,

  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,

  reporter: process.env.CI
    ? [['html', { open: 'never' }], ['github'], ['list']]
    : [['html', { open: 'never' }], ['list']],

  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15 * 1000,
    navigationTimeout: 30 * 1000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: [
    {
      command: 'node e2e/scripts/start-backend.js',
      url: BACKEND_HEALTH_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120 * 1000,
      env: { E2E_BACKEND_PORT: BACKEND_PORT },
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: BASE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 60 * 1000,
      env: { VITE_API_BASE_URL: `http://127.0.0.1:${BACKEND_PORT}` },
    },
  ],
})
