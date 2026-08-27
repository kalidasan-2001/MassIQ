// E2E-04 -- A browser reload must not destroy persisted domain state. This
// exercises the actual product requirement: a user can close and reopen
// the app and find their confirmed LegendEntry exactly as they left it.
const { test, expect } = require('@playwright/test')
const { attachMonitoring } = require('../helpers/monitoring')
const {
  uniqueName,
  createProject,
  uploadPlan,
  waitForPersistedPreview,
  createLegendEntry,
  dragSelectRegion,
  runOcr,
  saveCorrection,
  confirmLegendEntry,
  r3Section,
} = require('../helpers/app-actions')
const { PATTERN_REGION, DESCRIPTION_REGION } = require('../fixtures/fixture-regions')

test.describe('E2E-04: persistence across reload', () => {
  test('confirmed LegendEntry survives a full page reload', async ({ page }) => {
    const monitor = attachMonitoring(page)

    const projectName = uniqueName('E2E Persistence Project')
    const correctedText = 'Persisted description text (E2E)'
    const materialName = 'Persisted Material Name'

    await page.goto('/')
    await createProject(page, projectName)
    await uploadPlan(page)
    await waitForPersistedPreview(page)
    await createLegendEntry(page)
    await dragSelectRegion(page, 'pattern', PATTERN_REGION)
    await dragSelectRegion(page, 'description', DESCRIPTION_REGION)
    await runOcr(page)
    await saveCorrection(page, { correctedText, materialName, thicknessMm: 150 })
    await confirmLegendEntry(page)
    await expect(page.getByTestId('legend-status-pill')).toHaveText('confirmed')

    // Simulate closing/reopening the app.
    await page.reload({ waitUntil: 'networkidle' })

    // State resets client-side on reload -- re-select the same project and
    // plan through the UI exactly as a returning user would.
    const section = r3Section(page)
    await section.locator('select').first().selectOption({ label: projectName })
    await page.waitForFunction(
      (label) => {
        const select = document.querySelectorAll('select')[1]
        return select && select.options.length > 1
      },
      null,
      { timeout: 10000 }
    )
    await section.locator('select').nth(1).selectOption({ index: 1 })

    // The confirmed entry must reappear in the list purely from server
    // state -- nothing here was re-created. Matched by class + exact
    // text, not a bare text search: the editor (once an entry is loaded)
    // renders its own "Confirmed"/"confirmed" text too -- see
    // legend-workflow.spec.js's comment on the same ambiguity.
    await expect(page.locator('.status-pill', { hasText: /^Confirmed$/ })).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(materialName)).toBeVisible()

    // Load it into the editor and verify every meaningful field is intact.
    await page.getByText(materialName).click()
    await expect(page.locator('#legend-corrected-text')).toHaveValue(correctedText)
    await expect(page.locator('#legend-material-name')).toHaveValue(materialName)
    await expect(page.locator('#legend-thickness-mm')).toHaveValue('150')
    await expect(page.getByTestId('legend-status-pill')).toHaveText('confirmed')
    await expect(page.getByTestId('confirm-btn')).toBeDisabled()

    monitor.assertClean()
  })
})
