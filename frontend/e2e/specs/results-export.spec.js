// E2E-08 -- R8: Results and Export, driven entirely through the real UI
// with real Chromium pointer/mouse input and a REAL browser download
// event (R8 sections 35-36). No page.evaluate() state injection, and the
// export is never invoked via a direct API call as the primary proof --
// it is a real click on the Export button, followed by real Playwright
// download handling.
const fs = require('fs')
const { test, expect } = require('@playwright/test')
const { attachMonitoring } = require('../helpers/monitoring')
const {
  uniqueName,
  createProject,
  uploadPlan,
  waitForPersistedPreview,
  createLegendEntry,
  dragSelectRegion,
  confirmDeclaredScale,
  calculateQuantity,
  confirmQuantityResult,
  runOcr,
  saveCorrection,
  confirmLegendEntry,
  r3Section,
} = require('../helpers/app-actions')
const { PATTERN_REGION, DESCRIPTION_REGION } = require('../fixtures/fixture-regions')

test.describe('E2E-08: Results and Export (real pointer/mouse input, real download)', () => {
  test('review -> confirm quantity -> Results shows it -> real Excel download', async ({ page }) => {
    const monitor = attachMonitoring(page)

    const projectName = uniqueName('E2E Results Project')
    await page.goto('/')
    await createProject(page, projectName)
    await uploadPlan(page)
    await waitForPersistedPreview(page)

    // -- Confirmed reference LegendEntry + computed features --
    await createLegendEntry(page)
    await dragSelectRegion(page, 'pattern', PATTERN_REGION)
    await expect(page.getByAltText('Selected hatch pattern')).toBeVisible()
    await dragSelectRegion(page, 'description', DESCRIPTION_REGION)
    await expect(page.getByAltText('Selected description')).toBeVisible()
    await runOcr(page)
    await saveCorrection(page, {
      correctedText: 'Stahlbeton C25/30, d=20 cm (results reference)',
      materialName: 'Stahlbeton C25/30',
      thicknessMm: 200,
    })
    const confirmResponse = await confirmLegendEntry(page)
    expect(confirmResponse.status()).toBe(200)

    const computeFeaturesResponse = page.waitForResponse(
      (res) => res.url().includes('/features') && res.request().method() === 'POST'
    )
    await page.getByTestId('compute-features-btn').click()
    await computeFeaturesResponse
    await expect(page.getByText('Computed', { exact: true })).toBeVisible()

    // -- Run Detection V2, accept one real candidate --
    const runResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/detection-runs') && res.request().method() === 'POST'
    )
    await page.getByTestId('run-detection-btn').click()
    const runResponse = await runResponsePromise
    const runBody = await runResponse.json()
    expect(runBody.status).toBe('completed')
    await expect(page.getByTestId('detected-region-list')).toBeVisible()

    const acceptResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/regions/') && res.request().method() === 'PATCH'
    )
    await page.getByTestId('accept-region-btn').first().click()
    await acceptResponsePromise
    await expect(page.getByTestId('detected-region-list').getByText('accepted')).toBeVisible()

    // -- Confirm scale, set dimension, calculate quantity --
    const scaleResponse = await confirmDeclaredScale(page, 100)
    expect(scaleResponse.status()).toBe(200)

    const quantityResponse = await calculateQuantity(page, 0.2)
    expect(quantityResponse.status()).toBe(200)
    const quantityBody = await quantityResponse.json()
    expect(quantityBody.status).toBe('draft')
    expect(quantityBody.final_area_m2).toBeGreaterThan(0)
    expect(quantityBody.volume_m3).toBeGreaterThan(0)

    // -- Confirm the quantity result (draft -> confirmed) --
    const confirmQuantityResponse = await confirmQuantityResult(page)
    expect(confirmQuantityResponse.status()).toBe(200)
    const confirmedBody = await confirmQuantityResponse.json()
    expect(confirmedBody.status).toBe('confirmed')

    // -- "Navigate" to Results (rendered on the same project-scoped page,
    // per R8 section 22 -- no navigation redesign) and verify the
    // confirmed result appears with matching area/volume. --
    const resultsPanel = page.getByTestId('results-panel')
    await resultsPanel.scrollIntoViewIfNeeded()
    await expect(page.getByTestId('results-table')).toBeVisible({ timeout: 10000 })
    const resultRow = page.getByTestId('result-row').filter({ hasText: 'Stahlbeton C25/30' })
    await expect(resultRow).toBeVisible()
    await expect(resultRow.getByTestId('result-status')).toHaveText('Confirmed')

    const expectedArea = quantityBody.final_area_m2.toFixed(2)
    const expectedVolume = quantityBody.volume_m3.toFixed(3)
    await expect(resultRow.getByTestId('result-area')).toHaveText(expectedArea)
    await expect(resultRow.getByTestId('result-volume')).toHaveText(expectedVolume)

    // -- Real Excel export: real click, real browser download event, not
    // a direct API call as the primary proof (R8 sections 35-36). --
    const exportButton = page.getByTestId('export-results-btn')
    await expect(exportButton).toContainText('(1)')
    await expect(exportButton).toBeEnabled()

    const [download] = await Promise.all([page.waitForEvent('download'), exportButton.click()])

    const filename = download.suggestedFilename()
    expect(filename).toMatch(/^MassIQ_.*_quantities_\d{8}\.xlsx$/)

    const downloadPath = await download.path()
    expect(downloadPath).toBeTruthy()
    const stats = fs.statSync(downloadPath)
    expect(stats.size).toBeGreaterThan(0)

    await expect(page.getByTestId('export-status')).toHaveText('Export downloaded.')

    // -- Reload: the confirmed result must persist purely from server
    // state (R8 section 32's spirit / R7's own established discipline). --
    await page.reload({ waitUntil: 'networkidle' })
    const section = r3Section(page)
    await section.locator('select').first().selectOption({ label: projectName })
    await page.waitForFunction(
      () => {
        const select = document.querySelectorAll('select')[1]
        return select && select.options.length > 1
      },
      null,
      { timeout: 10000 }
    )
    await section.locator('select').nth(1).selectOption({ index: 1 })

    await expect(page.getByTestId('results-table')).toBeVisible({ timeout: 10000 })
    const reloadedRow = page.getByTestId('result-row').filter({ hasText: 'Stahlbeton C25/30' })
    await expect(reloadedRow).toBeVisible()
    await expect(reloadedRow.getByTestId('result-status')).toHaveText('Confirmed')
    await expect(reloadedRow.getByTestId('result-area')).toHaveText(expectedArea)

    monitor.assertClean()
  })

  // -- R8 section 38: draft results are visible but excluded from export --
  test('a draft quantity shows as Draft and is excluded from export until confirmed', async ({ page }) => {
    const monitor = attachMonitoring(page)

    const projectName = uniqueName('E2E Draft Results Project')
    await page.goto('/')
    await createProject(page, projectName)
    await uploadPlan(page)
    await waitForPersistedPreview(page)

    await createLegendEntry(page)
    await dragSelectRegion(page, 'pattern', PATTERN_REGION)
    await dragSelectRegion(page, 'description', DESCRIPTION_REGION)
    await runOcr(page)
    await saveCorrection(page, {
      correctedText: 'Stahlbeton C25/30, d=20 cm',
      materialName: 'Stahlbeton C25/30',
      thicknessMm: 200,
    })
    await confirmLegendEntry(page)

    const computeFeaturesResponse = page.waitForResponse(
      (res) => res.url().includes('/features') && res.request().method() === 'POST'
    )
    await page.getByTestId('compute-features-btn').click()
    await computeFeaturesResponse

    const runResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/detection-runs') && res.request().method() === 'POST'
    )
    await page.getByTestId('run-detection-btn').click()
    await runResponsePromise
    await expect(page.getByTestId('detected-region-list')).toBeVisible()

    const acceptResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/regions/') && res.request().method() === 'PATCH'
    )
    await page.getByTestId('accept-region-btn').first().click()
    await acceptResponsePromise

    await confirmDeclaredScale(page, 100)
    await calculateQuantity(page, 0.2)
    // Deliberately NOT confirming the quantity result -- stays DRAFT.

    const resultsPanel = page.getByTestId('results-panel')
    await resultsPanel.scrollIntoViewIfNeeded()
    await expect(page.getByTestId('results-table')).toBeVisible({ timeout: 10000 })
    const draftRow = page.getByTestId('result-row').filter({ hasText: 'Stahlbeton C25/30' })
    await expect(draftRow.getByTestId('result-status')).toHaveText('Draft')

    // Export button reflects zero CONFIRMED results, even though a DRAFT
    // result is visible in the table above it.
    const exportButton = page.getByTestId('export-results-btn')
    await expect(exportButton).toContainText('(0)')
    await expect(exportButton).toBeDisabled()
    await expect(page.getByTestId('export-disabled-hint')).toBeVisible()

    // Now confirm it -- the export count must change.
    await confirmQuantityResult(page)
    await resultsPanel.scrollIntoViewIfNeeded()
    await expect(exportButton).toContainText('(1)', { timeout: 10000 })
    await expect(exportButton).toBeEnabled()

    monitor.assertClean()
  })
})
