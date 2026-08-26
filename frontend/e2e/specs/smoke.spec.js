// E2E-01 -- Application smoke test. The fastest browser check: does the
// app load at all, with no fatal errors, against a live backend.
const { test, expect } = require('@playwright/test')
const { attachMonitoring } = require('../helpers/monitoring')

test.describe('E2E-01: application smoke @smoke', () => {
  test('page loads, critical UI appears, backend is healthy, no console/network failures', async ({
    page,
    request,
  }) => {
    const monitor = attachMonitoring(page)

    // Backend health, independent of the frontend -- confirms the
    // isolated E2E backend process is actually up before trusting any UI
    // assertion below. Hit it via its own known port directly rather than
    // through the frontend, since baseURL points at the frontend dev server.
    const backendPort = process.env.E2E_BACKEND_PORT || '8020'
    const backendHealth = await request.get(`http://127.0.0.1:${backendPort}/health`)
    expect(backendHealth.ok()).toBeTruthy()
    expect(await backendHealth.json()).toEqual({ status: 'ok' })

    await page.goto('/')

    // Legacy MVP hero + the new R3 section both present -- confirms the
    // whole app shell rendered, not just one half of it.
    await expect(page.getByRole('heading', { name: /Business MVP for automated quantity takeoff/i })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Legend Workflow (R3)' })).toBeVisible()

    monitor.assertClean()
  })
})
