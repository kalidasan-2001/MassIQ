// E2E-09 -- R9's most important acceptance test: the complete, real
// MassIQ product journey, driven entirely through the actual UI with
// real Chromium pointer/mouse input. No page.evaluate() state injection,
// no direct API calls for any of the critical actions below -- every
// LegendEntry, DetectedRegion decision, ManualRegionCorrection, and
// QuantityResult is created exactly the way a real user would create it.
//
// Covers R9 sections 33-36's required flow: Project -> Plans -> Plan
// Preparation -> Legend -> Materials -> Analysis -> Review -> Results ->
// Export -> reload -> reopen -> re-verify.
const fs = require('fs')
const { test, expect } = require('@playwright/test')
const { attachMonitoring } = require('../helpers/monitoring')
const {
  uniqueName,
  createProject,
  selectExistingProject,
  uploadPlan,
  waitForPersistedPreview,
  createLegendEntry,
  dragSelectRegion,
  dragManualCorrection,
  runOcr,
  saveCorrection,
  confirmLegendEntry,
  confirmDeclaredScale,
  calculateQuantity,
  confirmQuantityResult,
  gotoStage,
  r3Section,
} = require('../helpers/app-actions')
const { PATTERN_REGION, DESCRIPTION_REGION, EXPECTED_OCR_SUBSTRING } = require('../fixtures/fixture-regions')

const MANUAL_ADD_REGION = { x: 0.55, y: 0.62, width: 0.15, height: 0.15 }
const MANUAL_SUBTRACT_REGION = { x: 0.59, y: 0.66, width: 0.05, height: 0.05 }

test.describe('E2E-09: complete MassIQ project journey', () => {
  test('project -> plans -> plan preparation -> legend -> materials -> analysis -> review -> results -> export -> reload -> reopen', async ({
    page,
  }) => {
    test.setTimeout(120 * 1000)
    const monitor = attachMonitoring(page)

    const projectName = uniqueName('E2E-09 Project')
    const materialName = 'Stahlbeton C25/30'

    // 1-3: open MassIQ, create a Project, verify project landing/progress.
    await page.goto('/')
    await createProject(page, projectName)
    const section = r3Section(page)
    await expect(section.getByTestId('project-landing-summary')).toContainText('0 plans')
    await expect(section.getByTestId('workflow-nav')).toBeVisible()

    // 4-6: Plans -- upload synthetic construction PDF, wait for READY.
    await expect(section.getByTestId('plans-empty')).toBeVisible()
    await uploadPlan(page)
    const preview = await waitForPersistedPreview(page)
    await expect(preview).toBeVisible()
    await expect(section.getByTestId('plan-list')).toContainText('Ready')
    await expect(section.getByTestId('workflow-stage-status-plans')).toHaveText('Complete')

    // 7-9: Plan Preparation -- confirm scale, verify stage completes.
    await gotoStage(page, 'plan_preparation')
    await expect(section.getByTestId('workflow-stage-status-plan_preparation')).toHaveText('In progress')
    const scaleResponse = await confirmDeclaredScale(page, 100)
    expect(scaleResponse.status()).toBe(200)
    await expect(page.getByTestId('scale-status')).toHaveText(/Confirmed/)
    await expect(section.getByTestId('workflow-stage-status-plan_preparation')).toHaveText('Complete')

    // 10-17: Legend -- real mouse drag for hatch + description, OCR,
    // correct text, confirm material, compute hatch features.
    await gotoStage(page, 'legend')
    await createLegendEntry(page)
    await dragSelectRegion(page, 'pattern', PATTERN_REGION)
    await expect(page.getByAltText('Selected hatch pattern')).toBeVisible()
    await dragSelectRegion(page, 'description', DESCRIPTION_REGION)
    await expect(page.getByAltText('Selected description')).toBeVisible()
    await runOcr(page)
    const ocrText = await page.locator('#legend-raw-ocr-text').inputValue()
    expect(ocrText).toContain(EXPECTED_OCR_SUBSTRING)
    await saveCorrection(page, {
      correctedText: `${materialName}, d=20 cm (E2E-09 journey)`,
      materialName,
      thicknessMm: 200,
    })
    const confirmResponse = await confirmLegendEntry(page)
    expect(confirmResponse.status()).toBe(200)
    await expect(page.getByTestId('legend-status-pill')).toHaveText('confirmed')

    const computeFeaturesResponse = page.waitForResponse(
      (res) => res.url().includes('/features') && res.request().method() === 'POST'
    )
    await page.getByTestId('compute-features-btn').click()
    await computeFeaturesResponse
    await expect(page.getByText('Computed', { exact: true })).toBeVisible()
    await expect(section.getByTestId('workflow-stage-status-legend')).toHaveText('Complete')

    // 18-19: add the confirmed hatch to the Project Pattern Library,
    // verify Materials stage state.
    const addToLibraryResponse = page.waitForResponse(
      (res) => res.url().includes('/library') && res.request().method() === 'POST'
    )
    await page.getByTestId('add-to-library-btn').click()
    await addToLibraryResponse
    await expect(page.getByText('In Project Library', { exact: true })).toBeVisible()

    await gotoStage(page, 'materials')
    await expect(page.getByTestId('library-entry-list')).toBeVisible()
    await expect(page.getByTestId('library-entry').first()).toContainText(materialName)
    await expect(section.getByTestId('workflow-stage-status-materials')).toHaveText('Complete')

    // 20-22: Analysis -- run Detection V2, wait for candidate regions.
    await gotoStage(page, 'analysis')
    const runResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/detection-runs') && res.request().method() === 'POST'
    )
    await page.getByTestId('run-detection-btn').click()
    const runResponse = await runResponsePromise
    const runBody = await runResponse.json()
    expect(runBody.status).toBe('completed')
    expect(runBody.candidate_region_count).toBeGreaterThanOrEqual(2)
    await expect(page.getByTestId('detected-region-list')).toBeVisible()
    await expect(section.getByTestId('workflow-stage-status-analysis')).toHaveText('Complete')

    // 23-27: Review -- accept one candidate, reject another, real-mouse
    // manual ADD and SUBTRACT.
    await gotoStage(page, 'review')
    const acceptResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/regions/') && res.request().method() === 'PATCH'
    )
    await page.getByTestId('accept-region-btn').first().click()
    await acceptResponsePromise

    const rejectResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/regions/') && res.request().method() === 'PATCH'
    )
    await page.getByTestId('reject-region-btn').first().click()
    await rejectResponsePromise
    await expect(page.getByTestId('detected-region-list').getByText('accepted')).toBeVisible()
    await expect(page.getByTestId('detected-region-list').getByText('rejected')).toBeVisible()
    // Note: Review's own "Complete" stage status requires every candidate
    // region decided, not just one accept/reject pair -- the fixture can
    // produce more than 2 candidates, so that stage-status transition is
    // covered by deriveWorkflowStages.test.js instead of asserted here.

    const addResponse = await dragManualCorrection(page, 'add', MANUAL_ADD_REGION)
    expect(addResponse.status()).toBe(201)
    await expect(page.getByTestId('manual-overlay-add')).toBeVisible()

    const subtractResponse = await dragManualCorrection(page, 'subtract', MANUAL_SUBTRACT_REGION)
    expect(subtractResponse.status()).toBe(201)
    await expect(page.getByTestId('manual-overlay-subtract')).toBeVisible()

    // 28-30: confirm dimension, calculate, confirm QuantityResult.
    const quantityResponse = await calculateQuantity(page, 0.2)
    expect(quantityResponse.status()).toBe(200)
    const quantityBody = await quantityResponse.json()
    expect(quantityBody.final_area_m2).toBeGreaterThan(0)
    expect(quantityBody.volume_m3).toBeGreaterThan(0)
    await expect(page.getByTestId('quantity-status')).toHaveText('Draft')

    const confirmQuantityResponse = await confirmQuantityResult(page)
    expect(confirmQuantityResponse.status()).toBe(200)
    await expect(page.getByTestId('quantity-status')).toHaveText('Confirmed')
    await expect(section.getByTestId('workflow-stage-status-results')).toHaveText('Complete')

    const areaText = await page.getByTestId('quantity-area').textContent()
    const volumeText = await page.getByTestId('quantity-volume').textContent()

    // 31-34: Results -- verify material, authoritative area, volume.
    await gotoStage(page, 'results')
    const resultRow = page.getByTestId('result-row').filter({ hasText: materialName })
    await expect(resultRow).toBeVisible()
    await expect(resultRow.getByTestId('result-status')).toHaveText('Confirmed')
    const expectedArea = quantityBody.final_area_m2.toFixed(2)
    const expectedVolume = quantityBody.volume_m3.toFixed(3)
    await expect(resultRow.getByTestId('result-area')).toHaveText(expectedArea)
    await expect(resultRow.getByTestId('result-volume')).toHaveText(expectedVolume)

    // 35-38: real Excel export -- real click, real browser download.
    const exportButton = page.getByTestId('export-results-btn')
    await expect(exportButton).toBeEnabled()
    const [download] = await Promise.all([page.waitForEvent('download'), exportButton.click()])
    const filename = download.suggestedFilename()
    expect(filename).toMatch(/^MassIQ_.*_quantities_\d{8}\.xlsx$/)
    const downloadPath = await download.path()
    expect(downloadPath).toBeTruthy()
    expect(fs.statSync(downloadPath).size).toBeGreaterThan(0)

    // 39-42: reload, then a genuinely cold re-open (fresh navigation, no
    // URL state at all) of the same Project -- both must show the same
    // authoritative, coherent workflow state.
    await page.reload({ waitUntil: 'networkidle' })
    await expect(section.getByTestId('workflow-stage-status-results')).toHaveText('Complete')
    await expect(page.getByTestId('result-row').filter({ hasText: materialName })).toBeVisible()

    await page.goto('/')
    await selectExistingProject(page, projectName)
    await expect(page.getByTestId('result-row').filter({ hasText: materialName })).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('result-row').filter({ hasText: materialName }).getByTestId('result-status')).toHaveText(
      'Confirmed'
    )
    await expect(
      page.getByTestId('result-row').filter({ hasText: materialName }).getByTestId('result-area')
    ).toHaveText(expectedArea)

    // 43-44: zero unexpected console errors, zero unexpected 5xx.
    monitor.assertClean()
  })
})
