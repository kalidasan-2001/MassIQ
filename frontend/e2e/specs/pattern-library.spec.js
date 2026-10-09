// E2E-05 -- R5: the Project Pattern Library, driven entirely through the
// real UI with real Chromium pointer/mouse input (never by injecting
// component state directly -- see R3.5's "pointer-first testing"
// requirement, same discipline legend-workflow.spec.js already follows).
//
// Sequence: confirm a first LegendEntry -> compute its hatch features ->
// add it to the project's pattern library -> confirm a second, related
// hatch on the same page (the fixture PDF's own pattern region is reused,
// so both crops are genuinely, independently drawn selections of the
// same real pixel content -- a deterministic, real "related hatch" case
// without inventing a second fixture) -> compute its features -> request
// matches -> verify the first entry's material appears as a suggestion ->
// accept it -> reload -> verify the accepted decision persisted.
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

async function confirmOneLegendEntry(page, { correctedText, materialName }) {
  await createLegendEntry(page)
  await dragSelectRegion(page, 'pattern', PATTERN_REGION)
  await expect(page.getByAltText('Selected hatch pattern')).toBeVisible()
  await dragSelectRegion(page, 'description', DESCRIPTION_REGION)
  await expect(page.getByAltText('Selected description')).toBeVisible()
  await runOcr(page)
  await saveCorrection(page, { correctedText, materialName, thicknessMm: 200 })
  const confirmResponse = await confirmLegendEntry(page)
  expect(confirmResponse.status()).toBe(200)
}

test.describe('E2E-05: project pattern library (real pointer/mouse input)', () => {
  test('add a confirmed pattern to the library, then match a related hatch against it', async ({ page }) => {
    const monitor = attachMonitoring(page)

    const projectName = uniqueName('E2E Pattern Library Project')
    await page.goto('/')
    await createProject(page, projectName)
    await uploadPlan(page)
    await waitForPersistedPreview(page)

    // -- First LegendEntry: confirm, compute features, add to library --
    await confirmOneLegendEntry(page, {
      correctedText: 'Stahlbeton C25/30, d=20 cm (library source)',
      materialName: 'Stahlbeton C25/30',
    })

    const computeFeaturesResponse1 = page.waitForResponse(
      (res) => res.url().includes('/features') && res.request().method() === 'POST'
    )
    await page.getByTestId('compute-features-btn').click()
    await computeFeaturesResponse1
    await expect(page.getByText('Computed', { exact: true })).toBeVisible()

    const addToLibraryResponse = page.waitForResponse(
      (res) => res.url().includes('/library') && res.request().method() === 'POST'
    )
    await page.getByTestId('add-to-library-btn').click()
    await addToLibraryResponse
    await expect(page.getByText('In Project Library')).toBeVisible()

    // Project Pattern Library section (project-scoped, below the workspace)
    // must reflect the new entry too.
    await expect(page.getByTestId('pattern-library-panel').getByText('Stahlbeton C25/30')).toBeVisible()

    // -- Second, related LegendEntry: same real pattern region, confirmed
    // independently -- genuinely different LegendEntry/crop file on disk,
    // same underlying pixels. --
    await confirmOneLegendEntry(page, {
      correctedText: 'Stahlbeton C25/30, d=20 cm (query)',
      materialName: 'Unconfirmed material',
    })

    const computeFeaturesResponse2 = page.waitForResponse(
      (res) => res.url().includes('/features') && res.request().method() === 'POST'
    )
    await page.getByTestId('compute-features-btn').click()
    await computeFeaturesResponse2
    await expect(page.getByText('Computed', { exact: true })).toBeVisible()

    // -- Request matches -- the first entry's material must appear. --
    const matchesResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/matches') && res.request().method() === 'POST'
    )
    await page.getByRole('button', { name: 'Find Matches' }).click()
    const matchesResponse = await matchesResponsePromise
    const matchesBody = await matchesResponse.json()
    expect(matchesBody.candidates.length).toBeGreaterThan(0)
    expect(matchesBody.candidates[0].canonical_material_name).toBe('Stahlbeton C25/30')

    await expect(page.getByTestId('match-candidate-list')).toBeVisible()
    await expect(page.getByTestId('match-candidate').first()).toContainText('Stahlbeton C25/30')
    await expect(page.getByTestId('match-candidate').first()).toContainText('Pattern similarity:')

    // -- Accept the suggestion -- must persist a decision. --
    const decisionResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/match-decision') && res.request().method() === 'POST'
    )
    await page.getByTestId('use-match-btn').first().click()
    const decisionResponse = await decisionResponsePromise
    expect(decisionResponse.status()).toBe(201)
    await expect(page.getByTestId('match-candidate').first().getByText('accepted')).toBeVisible()

    // Accepting a match prefills the material fields -- the user still
    // must explicitly save/confirm; nothing here silently overwrote the
    // LegendEntry itself.
    await expect(page.locator('#legend-material-name')).toHaveValue('Stahlbeton C25/30')

    // -- Reload: the decision (and the library, and computed features)
    // must all still be there, purely from server state. R9 adds
    // URL-based workflow state (section 30): project/plan/page are
    // restored automatically from the URL on reload. --
    await page.reload({ waitUntil: 'networkidle' })
    const section = r3Section(page)
    await waitForPersistedPreview(page)

    // Re-select the second (query) legend entry -- the most recently
    // created list item. The decision-history GET fires as soon as
    // PatternMatchesPanel mounts (on selection), so the listener must be
    // registered before the click that triggers it.
    const decisionsResponsePromise = page.waitForResponse((res) => res.url().includes('/match-decisions'))
    await page.getByText('Unconfirmed material').click()
    await decisionsResponsePromise
    await expect(page.getByText('Computed', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: 'Find Matches' }).click()
    await expect(page.getByTestId('match-candidate').first().getByText('accepted')).toBeVisible({ timeout: 10000 })

    monitor.assertClean()
  })
})
