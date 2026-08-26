// Negative browser scenario (R3.5 section 13): an invalid/fake upload must
// produce a controlled, visible error -- never a white screen, an
// unhandled exception, or a misleading "successful" Plan/entry state.
// Covers both surfaces that accept a PDF upload: the legacy /upload-pdf
// route and the new persisted Plan API, since both were hardened for
// exactly this case in R2.5/R2.
const { test, expect } = require('@playwright/test')
const { attachMonitoring } = require('../helpers/monitoring')
const { uniqueName, createProject, r3Section } = require('../helpers/app-actions')

const FAKE_PDF = { name: 'fake.pdf', mimeType: 'application/pdf', buffer: Buffer.from('this is not a real pdf file') }

test.describe('negative path: invalid PDF upload', () => {
  test('legacy /upload-pdf: fake PDF produces a controlled error, no white screen, no fake success', async ({
    page,
  }) => {
    const monitor = attachMonitoring(page)
    await page.goto('/')

    const legacy = page.locator('section').filter({ has: page.getByRole('button', { name: 'Upload Floor Plan PDF' }) })
    await legacy.locator('input[type="file"]').setInputFiles(FAKE_PDF)
    await legacy.getByRole('button', { name: 'Upload Floor Plan PDF' }).click()

    // Controlled, visible error -- not a blank/broken page.
    await expect(legacy.locator('.error')).toBeVisible({ timeout: 10000 })
    await expect(legacy.locator('.error')).not.toContainText('Traceback')

    // No misleading successful Plan state: PlanViewer must never mount.
    await expect(legacy.getByText('Recovered Plan Workspace')).toHaveCount(0)

    // The rest of the app must still be fully usable -- not a white screen.
    await expect(page.getByRole('heading', { name: 'Legend Workflow (R3)' })).toBeVisible()
    await expect(legacy.getByRole('button', { name: 'Upload Floor Plan PDF' })).toBeEnabled()

    // The console monitor only fails on unexpected errors/5xx -- a 400
    // response for this request is the expected, correct outcome, and is
    // not flagged by attachMonitoring (which only watches for 5xx).
    monitor.assertClean()
  })

  test('new Plan API: fake PDF produces a controlled error, project remains usable', async ({ page }) => {
    const monitor = attachMonitoring(page)
    await page.goto('/')

    await createProject(page, uniqueName('E2E Invalid Upload Project'))
    const section = r3Section(page)
    await section.locator('input[type="file"]').setInputFiles(FAKE_PDF)
    await section.getByRole('button', { name: 'Upload Plan' }).click()

    await expect(section.locator('.error')).toBeVisible({ timeout: 10000 })
    await expect(section.locator('.error')).not.toContainText('Traceback')

    // No misleading successful Plan state: the plan picker must not gain
    // a "ready" entry for this failed upload.
    await expect(section.locator('select').nth(1)).not.toContainText('ready')

    // The project itself must remain usable -- the failed upload must not
    // have broken the picker or the rest of the workflow.
    await expect(section.getByPlaceholder('New project name')).toBeEditable()

    monitor.assertClean()
  })
})
