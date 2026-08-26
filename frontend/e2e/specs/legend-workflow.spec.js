// E2E-03 -- The Legend workflow: the most important R3 regression. Every
// selection is driven with real Playwright pointer/mouse events on the
// actual plan preview image -- never by calling a React handler or
// dispatching synthetic state. This is the test class that exists
// specifically because unit/component tests (which call handlers directly)
// could not catch the native-image-drag bug found during R3 (see
// docs/releases/R3_LEGEND_WORKFLOW_CHECKLIST.md and
// docs/testing/BROWSER_E2E_STRATEGY.md).
const { test, expect } = require('@playwright/test')
const { attachMonitoring } = require('../helpers/monitoring')
const {
  uniqueName,
  createProject,
  uploadPlan,
  waitForPersistedPreview,
  createLegendEntry,
  dragSelectRegion,
  dragOverImageRegion,
  runOcr,
  saveCorrection,
  confirmLegendEntry,
} = require('../helpers/app-actions')
const { PATTERN_REGION, DESCRIPTION_REGION, EXPECTED_OCR_SUBSTRING } = require('../fixtures/fixture-regions')

async function setUpProjectAndPlan(page) {
  await page.goto('/')
  await createProject(page, uniqueName('E2E Legend Project'))
  await uploadPlan(page)
  await waitForPersistedPreview(page)
}

test.describe('E2E-03: legend workflow (real pointer/mouse input)', () => {
  test('select pattern, select description, OCR, correct, confirm', async ({ page }) => {
    const monitor = attachMonitoring(page)
    await setUpProjectAndPlan(page)

    await createLegendEntry(page)
    await expect(page.locator('.status-pill').last()).toHaveText('draft')

    // Real drag over the fixture's known hatch-pattern region.
    await dragSelectRegion(page, 'pattern', PATTERN_REGION)
    await expect(page.getByAltText('Selected hatch pattern')).toBeVisible()

    // Real drag over the fixture's known description-text region.
    await dragSelectRegion(page, 'description', DESCRIPTION_REGION)
    await expect(page.getByAltText('Selected description')).toBeVisible()

    await runOcr(page)
    const ocrText = await page.locator('#legend-raw-ocr-text').inputValue()
    expect(ocrText).toContain(EXPECTED_OCR_SUBSTRING)
    await expect(page.locator('.status-pill').last()).toHaveText('ocr_complete')

    await saveCorrection(page, {
      correctedText: 'Stahlbeton C25/30, d=20 cm (corrected by E2E)',
      materialName: 'Stahlbeton C25/30',
      thicknessMm: 200,
    })

    const confirmResponse = await confirmLegendEntry(page)
    expect(confirmResponse.status()).toBe(200)
    await expect(page.locator('.status-pill.status-completed').first()).toBeVisible()

    // The confirmed entry must also show up in the entry list, not only in
    // the editor panel -- a user-visible result, not an implementation
    // detail. Matched precisely by class + exact case-sensitive text:
    // the editor's own disabled Confirm button also renders the literal
    // text "Confirmed" once disabled, and the editor's own status pill
    // shows the raw lowercase "confirmed" -- ancestor-scoping by
    // "Legend Entries" text doesn't disambiguate either, since the R3
    // section's own outer wrapper is *also* a `.card.panel` containing
    // both. Only the list item's pill is a `.status-pill` with the exact
    // capitalized text "Confirmed".
    await expect(page.locator('.status-pill', { hasText: /^Confirmed$/ })).toBeVisible()

    monitor.assertClean()
  })

  test('drag regression: pointer down -> multiple moves -> up produces a valid selection', async ({ page }) => {
    // Explicit regression coverage for the R3 native-image-drag bug: an
    // <img> is draggable by default, and a mousedown-then-move on one
    // without draggable={false} makes Chromium hijack the gesture into a
    // native OS-level image drag after the first mousemove, silently
    // swallowing every further mousemove/mouseup a custom selection
    // handler needs. Asserted behaviorally (a real multi-step drag must
    // still produce a saved selection), not by inspecting the
    // `draggable` attribute -- the fix's implementation detail may change
    // later, but this observable behavior must not regress.
    const monitor = attachMonitoring(page)
    await setUpProjectAndPlan(page)
    await createLegendEntry(page)

    await page.getByRole('button', { name: 'Select Pattern' }).click()
    // dragOverImageRegion performs exactly "down -> multiple intermediate
    // moves -> up" (see its own doc comment) -- this is exactly the
    // sequence that silently stalled before the draggable={false} fix.
    await dragOverImageRegion(page, page.locator('img[alt^="Plan page"]'), PATTERN_REGION)

    // The observable, user-facing result of a completed selection: a
    // saved crop appears and the toolbar leaves "drawing" mode.
    await expect(page.getByAltText('Selected hatch pattern')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('button', { name: 'Select Pattern' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Drawing Pattern/ })).toHaveCount(0)

    monitor.assertClean()
  })
})
