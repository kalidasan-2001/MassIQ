// R9 section 37: prerequisite-blocking browser coverage. A new project
// must not let the user reach Analysis with no confirmed, feature-computed
// legend material -- and the blocked state must explain *why*, not just
// hide the stage (R9 section 7). Once the prerequisites are genuinely met
// through the real UI, Analysis must become available with no other change.
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

test.describe('R9: workflow prerequisite blocking (real UI)', () => {
  test('Analysis is blocked with an explanation until Legend + hatch features are ready, then becomes available', async ({
    page,
  }) => {
    const monitor = attachMonitoring(page)
    await page.goto('/')
    await createProject(page, uniqueName('E2E Prerequisites Project'))
    const section = r3Section(page)

    // No plan, no legend, no features yet -- Analysis must explain why,
    // not just be missing from the page.
    const analysisStage = page.locator('#stage-analysis')
    await expect(analysisStage.getByTestId('stage-blocked-reason')).toContainText(
      'Analysis is available after you confirm at least one legend material and compute its hatch features.'
    )
    await expect(analysisStage.getByTestId('run-detection-btn')).toHaveCount(0)
    await expect(section.getByTestId('workflow-stage-status-analysis')).toHaveText('Blocked')

    // Upload a plan -- Analysis stays blocked (a plan alone isn't enough).
    await uploadPlan(page)
    await waitForPersistedPreview(page)
    await expect(analysisStage.getByTestId('stage-blocked-reason')).toBeVisible()

    // Confirm a legend entry -- Analysis is STILL blocked (needs computed
    // hatch features too, not just a confirmed material).
    await createLegendEntry(page)
    await dragSelectRegion(page, 'pattern', PATTERN_REGION)
    await dragSelectRegion(page, 'description', DESCRIPTION_REGION)
    await runOcr(page)
    await saveCorrection(page, {
      correctedText: 'Stahlbeton C25/30, d=20 cm (prerequisite check)',
      materialName: 'Stahlbeton C25/30',
      thicknessMm: 200,
    })
    await confirmLegendEntry(page)
    await expect(page.getByTestId('legend-status-pill')).toHaveText('confirmed')
    await expect(analysisStage.getByTestId('stage-blocked-reason')).toBeVisible()
    await expect(section.getByTestId('workflow-stage-status-analysis')).toHaveText('Blocked')

    // Compute hatch features -- the real, complete prerequisite. Analysis
    // must now become available with no other action.
    const computeFeaturesResponse = page.waitForResponse(
      (res) => res.url().includes('/features') && res.request().method() === 'POST'
    )
    await page.getByTestId('compute-features-btn').click()
    await computeFeaturesResponse

    await expect(analysisStage.getByTestId('stage-blocked-reason')).toHaveCount(0)
    await expect(analysisStage.getByTestId('run-detection-btn')).toBeVisible()
    await expect(section.getByTestId('workflow-stage-status-analysis')).toHaveText('In progress')

    monitor.assertClean()
  })
})
