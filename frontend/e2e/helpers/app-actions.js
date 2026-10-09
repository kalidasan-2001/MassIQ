// Reusable, UI-driving action helpers shared across specs. Every function
// here interacts through the real DOM (clicks, real pointer/mouse events,
// form fills) -- never by calling a React handler or component function
// directly, and never by dispatching synthetic React state. See R3.5's
// "pointer-first testing" requirement and docs/testing/BROWSER_E2E_STRATEGY.md.

const path = require('path')

const FIXTURE_PDF = path.resolve(__dirname, '..', 'fixtures', 'plan-fixture.pdf')

function uniqueName(prefix) {
  return `${prefix} ${Date.now()}-${Math.floor(Math.random() * 100000)}`
}

/** Scopes every locator to the persisted-project workflow section so
 * nothing here ever accidentally matches the legacy UploadPanel/PlanViewer
 * markup, which has its own similarly-named controls (file input,
 * "Select"-style buttons, etc). Named r3Section for historical reasons
 * (introduced in R3); R9 renamed the on-page heading to "Project Workflow"
 * but every spec that already imports r3Section keeps working unchanged. */
function r3Section(page) {
  return page.getByTestId('project-workflow-root')
}

/** R9: clicks a stage tab in the WorkflowNav (e.g. 'legend', 'analysis',
 * 'plan_preparation') to make that stage's pane active, overriding
 * whichever stage auto-advance currently has selected. */
async function gotoStage(page, stageKey) {
  await page.getByTestId(`workflow-stage-${stageKey}`).click()
}

async function createProject(page, name) {
  const section = r3Section(page)
  await section.getByPlaceholder('New project name').fill(name)
  await section.getByRole('button', { name: 'Create' }).click()
  // Confirms the project actually landed in the picker (server round-trip
  // complete), not just that the click happened.
  await page.waitForFunction(
    (projectName) => {
      const select = document.querySelectorAll('select')[0]
      return select && [...select.options].some((o) => o.text === projectName)
    },
    name
  )
}

/** R9 E2E-09: re-selects an already-existing project from the picker --
 * for proving persistence survives a genuinely cold navigation (goto('/')
 * with no query params), distinct from a same-URL reload (which restores
 * via useWorkflowUrlState instead -- see ProjectWorkflow.jsx). */
async function selectExistingProject(page, name) {
  const section = r3Section(page)
  await section.locator('select').first().selectOption({ label: name })
}

async function uploadPlan(page, { pdfPath = FIXTURE_PDF } = {}) {
  const section = r3Section(page)
  // Waits on the real network response rather than polling for a specific
  // DOM element: R9's stage navigation means the Plans stage's own picker
  // can legitimately unmount (auto-advancing to Legend) the instant the
  // upload succeeds, so asserting against a some-select's-options snapshot
  // is a race. Every other mutating helper in this file already waits on
  // its response the same way (confirmDeclaredScale, calculateQuantity,
  // etc.) -- this just matches that established, more robust pattern.
  const responsePromise = page.waitForResponse(
    (res) => /\/plans$/.test(new URL(res.url()).pathname) && res.request().method() === 'POST'
  )
  await section.locator('input[type="file"]').setInputFiles(pdfPath)
  await section.getByRole('button', { name: 'Upload Plan' }).click()
  await responsePromise
}

async function waitForPersistedPreview(page) {
  const img = page.locator('img[alt^="Plan page"]')
  await img.waitFor({ state: 'visible' })
  await page.waitForFunction(() => {
    const el = document.querySelector('img[alt^="Plan page"]')
    return el && el.complete && el.naturalWidth > 0
  })
  return img
}

async function createLegendEntry(page) {
  await page.getByRole('button', { name: '+ New Legend Entry' }).click()
  await page.getByText('Legend Entry', { exact: true }).waitFor({ state: 'visible' })
}

/**
 * Drags a real pointer over `imageLocator` to select `region` (a
 * normalized {x, y, width, height} rect -- see
 * e2e/fixtures/fixture-regions.js), converted here to real viewport pixel
 * coordinates against the *actual currently rendered* image, exactly
 * mirroring what a real user's mouse does. Never touches React state or
 * component internals directly -- this is the interaction pattern that
 * exists specifically because a synthetic-handler-only test previously
 * missed the native image-drag bug (see R3_LEGEND_WORKFLOW_CHECKLIST.md).
 *
 * Always scrolls the image into view first and re-reads its bounding box
 * afterward: at the default 1280x720 desktop viewport, the plan preview
 * routinely sits below the fold beneath the workflow-step grid and
 * upload/legend-assistant controls above it, and a bounding box read
 * before scrolling can be stale (or simply wrong) once the page has
 * scrolled -- a real drag would then land on whatever now occupies those
 * coordinates instead of the image.
 */
async function dragOverImageRegion(page, imageLocator, region) {
  await imageLocator.scrollIntoViewIfNeeded()
  const box = await imageLocator.boundingBox()
  if (!box) throw new Error('Target image has no bounding box -- is it rendered?')

  const startX = box.x + region.x * box.width
  const startY = box.y + region.y * box.height
  const endX = box.x + (region.x + region.width) * box.width
  const endY = box.y + (region.y + region.height) * box.height
  const midX = (startX + endX) / 2
  const midY = (startY + endY) / 2

  // Real pointer sequence: down, at least one intermediate move, then up.
  // A single down+up with no intermediate move would not exercise the same
  // code path a real drag does (see usePageSelection.js's onMouseMove
  // requirement) and would not have caught the R3 native-drag regression.
  await page.mouse.move(startX, startY)
  await page.mouse.down()
  await page.mouse.move(midX, midY)
  await page.mouse.move(endX, endY)
  await page.mouse.up()
}

/** R3 Legend workspace: clicks "Select Pattern"/"Select Description" first,
 * then drags over the persisted plan page preview. */
async function dragSelectRegion(page, mode, region) {
  const buttonName = mode === 'pattern' ? 'Select Pattern' : 'Select Description'
  await page.getByRole('button', { name: buttonName }).click()
  await dragOverImageRegion(page, page.locator('img[alt^="Plan page"]'), region)
}

async function runOcr(page) {
  await page.getByRole('button', { name: 'Run OCR' }).click()
  await page.waitForFunction(() => {
    const textarea = document.getElementById('legend-raw-ocr-text')
    return textarea && textarea.value.trim().length > 0
  })
}

async function saveCorrection(page, { correctedText, materialName, materialCode, thicknessMm } = {}) {
  if (correctedText !== undefined) {
    // A single .fill() atomically replaces the whole value -- an extra
    // preceding .fill('') was tried here originally and caused a real,
    // reproducible race against this field's OCR-seeding useEffect
    // (LegendEntryEditor.jsx), sometimes leaving the DOM's actual value
    // one React commit behind what was intended. One fill call avoids the
    // extra state transition entirely.
    await page.locator('#legend-corrected-text').fill(correctedText)
  }
  if (materialName !== undefined) {
    await page.locator('#legend-material-name').fill(materialName)
  }
  if (materialCode !== undefined) {
    await page.locator('#legend-material-code').fill(materialCode)
  }
  if (thicknessMm !== undefined) {
    await page.locator('#legend-thickness-mm').fill(String(thicknessMm))
  }
  await page.getByTestId('save-correction-btn').click()
}

async function confirmLegendEntry(page) {
  const responsePromise = page.waitForResponse((res) => res.url().includes('/confirm'))
  await page.getByTestId('confirm-btn').click()
  const response = await responsePromise
  return response
}

/**
 * R7: clicks Manual Add/Subtract first, then drags a REAL pointer over the
 * plan image -- same technique (and same reason) as dragSelectRegion.
 * `kind` is 'add' | 'subtract'.
 */
async function dragManualCorrection(page, kind, region) {
  const buttonTestId = kind === 'add' ? 'manual-add-btn' : 'manual-subtract-btn'
  const responsePromise = page.waitForResponse(
    (res) => res.url().includes('/manual-corrections') && res.request().method() === 'POST'
  )
  await page.getByTestId(buttonTestId).click()
  await dragOverImageRegion(page, page.locator('img[alt^="Plan page"]'), region)
  const response = await responsePromise
  return response
}

/** R7: confirms a declared (1:N) plan scale via the Quantity panel. */
async function confirmDeclaredScale(page, ratio) {
  const responsePromise = page.waitForResponse(
    (res) => res.url().includes('/scale') && res.request().method() === 'PUT'
  )
  await page.getByTestId('declared-ratio-input').fill(String(ratio))
  await page.getByTestId('confirm-scale-btn').click()
  const response = await responsePromise
  return response
}

/** R7: confirms the height/thickness dimension and calculates the
 * authoritative backend QuantityResult. */
async function calculateQuantity(page, dimensionM) {
  const responsePromise = page.waitForResponse(
    (res) => res.url().includes('/quantity') && res.request().method() === 'POST'
  )
  await page.getByTestId('confirmed-dimension-input').fill(String(dimensionM))
  await page.getByTestId('calculate-quantity-btn').click()
  const response = await responsePromise
  return response
}

/** R8: confirms the current DRAFT QuantityResult, moving it into export
 * eligibility. */
async function confirmQuantityResult(page) {
  const responsePromise = page.waitForResponse(
    (res) => res.url().includes('/quantity/confirm') && res.request().method() === 'POST'
  )
  await page.getByTestId('confirm-quantity-btn').click()
  const response = await responsePromise
  return response
}

module.exports = {
  FIXTURE_PDF,
  uniqueName,
  r3Section,
  gotoStage,
  createProject,
  selectExistingProject,
  uploadPlan,
  waitForPersistedPreview,
  createLegendEntry,
  dragOverImageRegion,
  dragSelectRegion,
  runOcr,
  saveCorrection,
  confirmLegendEntry,
  dragManualCorrection,
  confirmDeclaredScale,
  calculateQuantity,
  confirmQuantityResult,
}
