// R9 section 22/38: downstream invalidation must be reflected correctly,
// not cached. A CONFIRMED QuantityResult that gets recalculated after a
// geometry change (a new manual correction) must revert to DRAFT --
// proving workflow progress/state is derived from persisted truth, not a
// stale UI flag -- and Results must stop presenting it as unchanged final
// truth (R7's own recalculation authority: quantity_service.calculate()
// always sets status back to DRAFT and clears confirmed_at).
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
  runOcr,
  saveCorrection,
  confirmLegendEntry,
  confirmDeclaredScale,
  calculateQuantity,
  confirmQuantityResult,
} = require('../helpers/app-actions')
const { PATTERN_REGION, DESCRIPTION_REGION } = require('../fixtures/fixture-regions')

const MANUAL_ADD_REGION = { x: 0.55, y: 0.62, width: 0.15, height: 0.15 }
const SECOND_MANUAL_ADD_REGION = { x: 0.15, y: 0.72, width: 0.1, height: 0.08 }

test.describe('R9: quantity invalidation reflects real state (real UI)', () => {
  test('a CONFIRMED quantity reverts to DRAFT after a geometry change and recalculation, and Results reflects it', async ({
    page,
  }) => {
    test.setTimeout(60 * 1000)
    const monitor = attachMonitoring(page)
    await page.goto('/')
    await createProject(page, uniqueName('E2E Invalidation Project'))
    await uploadPlan(page)
    await waitForPersistedPreview(page)

    await createLegendEntry(page)
    await dragSelectRegion(page, 'pattern', PATTERN_REGION)
    await dragSelectRegion(page, 'description', DESCRIPTION_REGION)
    await runOcr(page)
    await saveCorrection(page, {
      correctedText: 'Stahlbeton C25/30, d=20 cm (invalidation check)',
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

    const addResponse = await dragManualCorrection(page, 'add', MANUAL_ADD_REGION)
    expect(addResponse.status()).toBe(201)

    await confirmDeclaredScale(page, 100)
    await calculateQuantity(page, 0.2)
    await expect(page.getByTestId('quantity-status')).toHaveText('Draft')

    const confirmQuantityResponse = await confirmQuantityResult(page)
    expect(confirmQuantityResponse.status()).toBe(200)
    await expect(page.getByTestId('quantity-status')).toHaveText('Confirmed')

    // Results must show it as Confirmed right now.
    const resultsStage = page.locator('#stage-results')
    const resultRow = resultsStage.getByTestId('result-row').filter({ hasText: 'Stahlbeton C25/30' })
    await expect(resultRow.getByTestId('result-status')).toHaveText('Confirmed')

    // -- Return to Review, change the geometry (one more manual ADD),
    // then recalculate. R7's authority: calculate() always resets status
    // to DRAFT and clears confirmed_at, regardless of prior CONFIRMED
    // state -- this is not automatic on correction alone, it happens on
    // the next explicit recalculation, exactly as a real user would do
    // after noticing they need one more correction. --
    const secondAddResponse = await dragManualCorrection(page, 'add', SECOND_MANUAL_ADD_REGION)
    expect(secondAddResponse.status()).toBe(201)
    await expect(page.getByTestId('manual-correction-counts')).toContainText('2 manual additions')

    // The quantity panel must still show the now-stale CONFIRMED number
    // until the user explicitly recalculates -- no silent background
    // recompute.
    await expect(page.getByTestId('quantity-status')).toHaveText('Confirmed')

    const recalculateResponse = await calculateQuantity(page, 0.2)
    expect(recalculateResponse.status()).toBe(200)
    const recalculatedBody = await recalculateResponse.json()
    expect(recalculatedBody.status).toBe('draft')

    await expect(page.getByTestId('quantity-status')).toHaveText('Draft')
    await expect(page.getByTestId('confirm-quantity-btn')).toBeVisible()

    // Results must no longer present it as unchanged final truth.
    await expect(resultRow.getByTestId('result-status')).toHaveText('Draft')

    monitor.assertClean()
  })
})
