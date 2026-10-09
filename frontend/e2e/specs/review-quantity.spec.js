// E2E-07 -- R7: Review & Deterministic Quantity Integration, driven
// entirely through the real UI with real Chromium pointer/mouse input
// (same "pointer-first testing" discipline as detection-v2.spec.js/
// legend-workflow.spec.js -- see R3.5's finding that a synthetic-handler
// -only test previously missed a real native-image-drag bug). No
// page.evaluate() state injection anywhere in this file (R7 section 33).
const { test, expect } = require('@playwright/test')
const { attachMonitoring } = require('../helpers/monitoring')
const {
  uniqueName,
  createProject,
  uploadPlan,
  waitForPersistedPreview,
  createLegendEntry,
  dragSelectRegion,
  dragManualCorrection,
  confirmDeclaredScale,
  calculateQuantity,
  runOcr,
  saveCorrection,
  confirmLegendEntry,
  r3Section,
} = require('../helpers/app-actions')
const { PATTERN_REGION, DESCRIPTION_REGION } = require('../fixtures/fixture-regions')

// Arbitrary, blank-whitespace areas of the fixture page (well clear of the
// pattern/description/second-pattern regions baked into the PDF) -- a
// manual correction can be drawn anywhere, it does not need real hatch
// content underneath it. SUBTRACT is drawn fully inside ADD so the
// interaction is geometrically meaningful, not just two disjoint boxes.
const MANUAL_ADD_REGION = { x: 0.55, y: 0.62, width: 0.15, height: 0.15 }
const MANUAL_SUBTRACT_REGION = { x: 0.59, y: 0.66, width: 0.05, height: 0.05 }

test.describe('E2E-07: Review & Quantity workflow (real pointer/mouse input)', () => {
  test('full review -> manual corrections -> scale -> dimension -> quantity, persisted across reload', async ({
    page,
  }) => {
    const monitor = attachMonitoring(page)

    const projectName = uniqueName('E2E Quantity Project')
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
      correctedText: 'Stahlbeton C25/30, d=20 cm (quantity reference)',
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

    // -- Run Detection V2 --
    const runResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/detection-runs') && res.request().method() === 'POST'
    )
    await page.getByTestId('run-detection-btn').click()
    const runResponse = await runResponsePromise
    const runBody = await runResponse.json()
    expect(runBody.status).toBe('completed')
    expect(runBody.candidate_region_count).toBeGreaterThanOrEqual(2)
    await expect(page.getByTestId('detected-region-list')).toBeVisible()

    // -- Accept one candidate, reject another (R7 section 3: only ACCEPTED
    // ever contributes to quantity) --
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

    // -- Manual Add, then Manual Subtract, both via real mouse drag --
    await expect(page.getByTestId('manual-add-btn')).toBeVisible()
    const addResponse = await dragManualCorrection(page, 'add', MANUAL_ADD_REGION)
    expect(addResponse.status()).toBe(201)
    await expect(page.getByTestId('manual-overlay-add')).toBeVisible()
    await expect(page.getByTestId('manual-correction-counts')).toContainText('1 manual addition')

    const subtractResponse = await dragManualCorrection(page, 'subtract', MANUAL_SUBTRACT_REGION)
    expect(subtractResponse.status()).toBe(201)
    await expect(page.getByTestId('manual-overlay-subtract')).toBeVisible()
    await expect(page.getByTestId('manual-correction-counts')).toContainText('1 manual subtraction')

    // -- Coordinate resilience across a viewport resize (R7 section 36):
    // the manual Add overlay is stored as a normalized [0,1] page fraction
    // (see coordinates.js), not raw CSS pixels -- it must stay over the
    // SAME physical plan region (the same fraction of the image) after the
    // browser window changes size, not drift to a fixed pixel offset. --
    const planImage = page.locator('img[alt^="Plan page"]')
    const imageBoxBefore = await planImage.boundingBox()
    const overlayBoxBefore = await page.getByTestId('manual-overlay-add').boundingBox()
    const fractionBefore = {
      x: (overlayBoxBefore.x - imageBoxBefore.x) / imageBoxBefore.width,
      y: (overlayBoxBefore.y - imageBoxBefore.y) / imageBoxBefore.height,
    }

    const originalViewport = page.viewportSize()
    await page.setViewportSize({ width: 900, height: originalViewport.height })

    const imageBoxAfter = await planImage.boundingBox()
    const overlayBoxAfter = await page.getByTestId('manual-overlay-add').boundingBox()
    const fractionAfter = {
      x: (overlayBoxAfter.x - imageBoxAfter.x) / imageBoxAfter.width,
      y: (overlayBoxAfter.y - imageBoxAfter.y) / imageBoxAfter.height,
    }
    // A defensible tolerance for sub-pixel rounding across two different
    // rendered widths, not an exact-pixel-match assumption.
    expect(Math.abs(fractionAfter.x - fractionBefore.x)).toBeLessThan(0.01)
    expect(Math.abs(fractionAfter.y - fractionBefore.y)).toBeLessThan(0.01)

    await page.setViewportSize(originalViewport)

    // -- Confirm scale, confirm dimension, calculate --
    const scaleResponse = await confirmDeclaredScale(page, 100)
    expect(scaleResponse.status()).toBe(200)
    await expect(page.getByTestId('scale-status')).toHaveText(/Confirmed/)

    const quantityResponse = await calculateQuantity(page, 0.2)
    expect(quantityResponse.status()).toBe(200)
    const quantityBody = await quantityResponse.json()
    expect(quantityBody.final_area_m2).toBeGreaterThan(0)
    expect(quantityBody.volume_m3).toBeGreaterThan(0)
    // Deterministic formula, independently re-checked here (R7 section 2):
    // volume = area * dimension.
    expect(quantityBody.volume_m3).toBeCloseTo(quantityBody.final_area_m2 * 0.2, 6)

    const areaText = await page.getByTestId('quantity-area').textContent()
    const volumeText = await page.getByTestId('quantity-volume').textContent()

    // -- Reload: every review/correction/scale/dimension/quantity decision
    // must persist purely from server state (R7 sections 29/49), same
    // pattern already proven by E2E-06/persistence.spec.js. R9 adds
    // URL-based workflow state (section 30): project/plan/page are
    // restored automatically from the URL on reload, no manual
    // re-selection needed. --
    await page.reload({ waitUntil: 'networkidle' })
    const section = r3Section(page)
    await waitForPersistedPreview(page)

    // Re-select the (only) legend entry so the features/detection panel
    // renders again (mirrors E2E-06). Scoped to the legend entry list
    // specifically -- R8's Results panel now also displays the material
    // name elsewhere on the same page, so an unscoped text match is
    // ambiguous.
    await section.getByTestId('legend-entry-list').getByText('Stahlbeton C25/30').first().click()
    await expect(page.getByText('Computed', { exact: true })).toBeVisible()

    await expect(page.getByTestId('detected-region-list')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('detected-region-list').getByText('accepted')).toBeVisible()
    await expect(page.getByTestId('detected-region-list').getByText('rejected')).toBeVisible()

    await expect(page.getByTestId('manual-correction-counts')).toContainText('1 manual addition', { timeout: 10000 })
    await expect(page.getByTestId('manual-correction-counts')).toContainText('1 manual subtraction')
    await expect(page.getByTestId('manual-overlay-add')).toBeVisible()
    await expect(page.getByTestId('manual-overlay-subtract')).toBeVisible()

    await expect(page.getByTestId('scale-status')).toHaveText(/Confirmed/)

    await expect(page.getByTestId('quantity-result')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('quantity-area')).toHaveText(areaText)
    await expect(page.getByTestId('quantity-volume')).toHaveText(volumeText)
    await expect(page.getByTestId('quantity-dimension')).toHaveText('0.200 m')

    monitor.assertClean()
  })

  // -- R7 section 37: unreviewed candidates must never affect quantity --
  test('unaccepted candidates contribute zero area to quantity', async ({ page }) => {
    const monitor = attachMonitoring(page)

    const projectName = uniqueName('E2E Zero Quantity Project')
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

    // Deliberately do NOT accept anything -- every candidate stays
    // CANDIDATE (the default status).
    const scaleResponse = await confirmDeclaredScale(page, 100)
    expect(scaleResponse.status()).toBe(200)

    const quantityResponse = await calculateQuantity(page, 0.2)
    expect(quantityResponse.status()).toBe(200)
    const body = await quantityResponse.json()
    expect(body.final_area_m2).toBe(0)
    expect(body.volume_m3).toBe(0)
    await expect(page.getByTestId('quantity-area')).toHaveText('0.00 m²')

    monitor.assertClean()
  })

  // -- R7 section 39: controlled feedback for invalid inputs, no unhandled
  // rejection / console error --
  test('calculating quantity before scale is confirmed shows a controlled error', async ({ page }) => {
    const monitor = attachMonitoring(page)

    const projectName = uniqueName('E2E Invalid Quantity Project')
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

    // The Calculate button is disabled until scale is confirmed -- a
    // controlled UI constraint, not a raw failed request the user has to
    // interpret.
    await expect(page.getByTestId('calculate-quantity-btn')).toBeDisabled()
    await expect(page.getByText('Confirm the drawing scale before calculating.')).toBeVisible()

    monitor.assertClean()
  })
})
