// E2E-06 -- R6: Detection Engine V2, driven entirely through the real UI
// with real Chromium pointer/mouse input (same "pointer-first testing"
// discipline as legend-workflow.spec.js/pattern-library.spec.js). The
// fixture PDF (plan-fixture.pdf) contains two independent, real hatch
// regions (see backend/scripts/generate_e2e_fixture.py) specifically so
// this test can accept one real candidate and reject another, not just
// exercise a single-region happy path.
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

test.describe('E2E-06: Detection Engine V2 (real pointer/mouse input)', () => {
  test('run detection, accept one candidate, reject another, and persist decisions across reload', async ({ page }) => {
    const monitor = attachMonitoring(page)

    const projectName = uniqueName('E2E Detection Project')
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
      correctedText: 'Stahlbeton C25/30, d=20 cm (detection reference)',
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

    // -- Run Detection V2 over the whole page --
    const runResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/detection-runs') && res.request().method() === 'POST'
    )
    await page.getByTestId('run-detection-btn').click()
    const runResponse = await runResponsePromise
    const runBody = await runResponse.json()
    expect(runBody.status).toBe('completed')
    // The fixture page has two real hatch regions -- expect at least 2
    // candidates, not just a single-region happy path.
    expect(runBody.candidate_region_count).toBeGreaterThanOrEqual(2)

    await expect(page.getByTestId('detected-region-list')).toBeVisible()
    const regionItems = page.getByTestId('detected-region')
    const regionCount = await regionItems.count()
    expect(regionCount).toBeGreaterThanOrEqual(2)

    // -- Accept the first candidate --
    const acceptResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/regions/') && res.request().method() === 'PATCH'
    )
    await page.getByTestId('accept-region-btn').first().click()
    const acceptResponse = await acceptResponsePromise
    expect(acceptResponse.status()).toBe(200)
    expect((await acceptResponse.json()).status).toBe('accepted')

    // -- Reject the next remaining candidate --
    const rejectResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/regions/') && res.request().method() === 'PATCH'
    )
    await page.getByTestId('reject-region-btn').first().click()
    const rejectResponse = await rejectResponsePromise
    expect(rejectResponse.status()).toBe(200)
    expect((await rejectResponse.json()).status).toBe('rejected')

    await expect(page.getByTestId('detected-region-list').getByText('accepted')).toBeVisible()
    await expect(page.getByTestId('detected-region-list').getByText('rejected')).toBeVisible()

    // -- Reload: run + region decisions must persist, purely from server
    // state (R6 section 24). --
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

    // Re-select the (only) legend entry so the features/detection panel
    // renders again. Scoped to the legend entry list specifically -- R8's
    // Results panel now also displays the material name elsewhere on the
    // same page, so an unscoped text match is ambiguous.
    await page.getByTestId('legend-entry-list').getByText('Stahlbeton C25/30').first().click()
    await expect(page.getByText('Computed', { exact: true })).toBeVisible()

    await expect(page.getByTestId('detected-region-list')).toBeVisible({ timeout: 10000 })
    await expect(page.getByTestId('detected-region-list').getByText('accepted')).toBeVisible()
    await expect(page.getByTestId('detected-region-list').getByText('rejected')).toBeVisible()

    monitor.assertClean()
  })
})
