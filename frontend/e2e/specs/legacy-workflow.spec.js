// E2E-05 -- Legacy MVP regression. The legacy workflow (UploadPanel.jsx ->
// PlanViewer.jsx, calling /upload-pdf, /save-hatch-sample, /detect-hatch,
// /export-excel) is a completely separate interface from the R3 Legend
// workflow's persisted Project/Plan pipeline -- see CLAUDE.md's
// architecture section. This spec exercises it end to end through its own
// real UI, exactly as R2.5/R3's audits describe it, without redesigning
// any of it.
//
// Exact test path: Upload PDF (UploadPanel) -> Confirm Plan Scale ->
// Select Component (Legend Assistant: drag hatch sample, confirm) ->
// Detection (auto-detect) -> Review Quantity (confirm review, confirm
// height) -> Export (download the Excel report).
const { test, expect } = require('@playwright/test')
const { attachMonitoring } = require('../helpers/monitoring')
const { FIXTURE_PDF, dragOverImageRegion } = require('../helpers/app-actions')
const { PATTERN_REGION } = require('../fixtures/fixture-regions')

function legacySection(page) {
  return page.locator('section').filter({ has: page.getByRole('button', { name: 'Upload Floor Plan PDF' }) })
}

test.describe('E2E-05: legacy MVP regression (real UI)', () => {
  test('upload -> scale -> hatch sample -> detection -> review -> quantity -> export', async ({ page }) => {
    test.setTimeout(90 * 1000)
    const monitor = attachMonitoring(page)
    await page.goto('/')

    const legacy = legacySection(page)
    await legacy.locator('input[type="file"]').setInputFiles(FIXTURE_PDF)
    await legacy.getByRole('button', { name: 'Upload Floor Plan PDF' }).click()
    await expect(legacy.getByText('Recovered Plan Workspace')).toBeVisible({ timeout: 15000 })

    // Step 1: confirm scale (defaults: 1000 px / 10 m = 100 px/m -- no
    // need to change the pre-filled values for this regression check).
    await legacy.getByRole('button', { name: 'Confirm Plan Scale' }).click()
    await expect(legacy.getByText('Scale status:')).toContainText('Confirmed')
    await legacy.getByRole('button', { name: 'Continue to Select Component' }).click()

    // Step 2: Legend Assistant -- real drag to select the hatch sample,
    // same draggable-image regression class as R3 (see PlanViewer.jsx's
    // draggable={false} fix applied alongside this release).
    await legacy.getByRole('button', { name: 'Open Legend Assistant' }).click()
    await legacy.getByRole('button', { name: 'Select Hatch Sample' }).click()

    const planImage = legacy.locator('img[alt="Uploaded floor plan preview"]')
    await dragOverImageRegion(page, planImage, PATTERN_REGION)

    await expect(legacy.getByText(/Hatch Sample: \d+ x \d+px/)).toBeVisible()
    await legacy.getByRole('button', { name: 'Confirm Hatch Sample' }).click()
    await expect(legacy.getByAltText('Hatch preview')).toBeVisible({ timeout: 10000 })

    // Step 3: run real backend hatch detection.
    await legacy.getByRole('button', { name: 'Open Detection' }).click()
    await legacy.getByRole('button', { name: 'Auto Detect Selected Component' }).click()
    await expect(legacy.getByText(/Backend returned \d+ detection/)).toBeVisible({ timeout: 15000 })
    await legacy.getByRole('button', { name: 'Continue to Review Quantity' }).click()

    // Step 4: review, height, quantity.
    const openReview = legacy.getByRole('button', { name: 'Open Review' })
    if (await openReview.isVisible().catch(() => false)) {
      await openReview.click()
    }
    // Every detection starts life as 'pending' (HatchDetectionPanel.jsx),
    // not 'accepted' -- the human-in-the-loop review step requires an
    // explicit accept per detection, matching the real user flow, not
    // just clicking "Confirm Review" with nothing selected.
    const acceptButtons = legacy.locator('.workflow-step').getByRole('button', { name: 'accepted' })
    const acceptCount = await acceptButtons.count()
    for (let i = 0; i < acceptCount; i += 1) {
      await acceptButtons.nth(i).click()
    }
    await legacy.getByRole('button', { name: 'Confirm Review' }).click()
    await expect(legacy.getByRole('heading', { name: 'Height Assistant' })).toBeVisible()

    await legacy.getByRole('button', { name: 'Open Height Assistant' }).click()
    await legacy.getByRole('button', { name: 'Confirm Height' }).click()
    await expect(legacy.getByText('Height status:')).toContainText('Confirmed')

    await expect(legacy.getByRole('heading', { name: 'Calculate Quantity' })).toBeVisible()
    await legacy.getByRole('button', { name: 'Continue to Export' }).click()

    // Step 5: export -- a real Excel file must actually download.
    await expect(legacy.getByRole('heading', { name: 'Export' })).toBeVisible()
    const downloadPromise = page.waitForEvent('download')
    await legacy.getByRole('button', { name: 'Export Quantity Report' }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe('massiq_quantity_report.xlsx')
    await expect(legacy.getByText('Excel report exported successfully.')).toBeVisible()

    monitor.assertClean()
  })
})
