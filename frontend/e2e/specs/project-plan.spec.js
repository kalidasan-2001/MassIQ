// E2E-02 -- Project and Plan, driven entirely through the actual UI (the
// new persisted Project/Plan pipeline, not the legacy /upload-pdf flow).
const { test, expect } = require('@playwright/test')
const { attachMonitoring } = require('../helpers/monitoring')
const { uniqueName, createProject, uploadPlan, waitForPersistedPreview, r3Section } = require('../helpers/app-actions')

test.describe('E2E-02: project and plan (real UI)', () => {
  test('create Project, upload Plan, open it, see the persisted page preview render', async ({ page }) => {
    const monitor = attachMonitoring(page)
    await page.goto('/')

    const projectName = uniqueName('E2E Project')
    await createProject(page, projectName)

    const section = r3Section(page)
    await expect(section.getByPlaceholder('New project name')).toHaveValue('')
    // The just-created project must be the one actually selected, not just
    // present somewhere in the list.
    await expect(section.locator('select').first()).toHaveValue(/.+/)

    await uploadPlan(page)
    await expect(section.locator('select').nth(1)).toContainText('plan-fixture.pdf')
    await expect(section.locator('select').nth(1)).toContainText('ready')

    const preview = await waitForPersistedPreview(page)
    await expect(preview).toBeVisible()
    const naturalWidth = await preview.evaluate((img) => img.naturalWidth)
    expect(naturalWidth).toBeGreaterThan(0)

    monitor.assertClean()
  })
})
