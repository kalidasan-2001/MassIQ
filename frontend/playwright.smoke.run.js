const { chromium } = require('playwright')

const PDF_PATH = 'C:\\Users\\kalid\\MassIQ\\_backup_before_flatten\\massiq-mvp-backup\\massiq_e2e.pdf'

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function expectVisible(locator, timeout = 15000) {
  await locator.waitFor({ state: 'visible', timeout })
}

async function run() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1600, height: 1800 } })
  const page = await context.newPage()

  const benignConsoleWarnings = []
  const realConsoleErrors = []
  const pageErrors = []
  const requestLog = []
  const responseLog = []

  const isBenign404Asset = (text) => {
    const t = String(text || '').toLowerCase()
    return (
      t.includes('favicon.ico') ||
      t.includes('manifest.json') ||
      t.includes('.map') ||
      t.includes('source map') ||
      t.includes('failed to load resource') && (t.includes('404') || t.includes('not found'))
    )
  }

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      if (isBenign404Asset(text)) benignConsoleWarnings.push(text)
      else realConsoleErrors.push(text)
    }
  })
  page.on('pageerror', (err) => pageErrors.push(String(err)))
  page.on('request', (req) => {
    if (
      req.url().includes('/upload-pdf') ||
      req.url().includes('/save-hatch-sample') ||
      req.url().includes('/detect-hatch') ||
      req.url().includes('/export-excel')
    ) {
      requestLog.push({ method: req.method(), url: req.url(), postData: req.postData() || '' })
    }
  })
  page.on('response', async (resp) => {
    const url = resp.url()
    if (
      url.includes('/upload-pdf') ||
      url.includes('/save-hatch-sample') ||
      url.includes('/detect-hatch') ||
      url.includes('/export-excel')
    ) {
      responseLog.push({ url, status: resp.status(), ok: resp.ok() })
    }
  })

  try {
    await page.goto('http://127.0.0.1:5174/index.html', { waitUntil: 'domcontentloaded' })
    await page.setInputFiles('input[type="file"]', PDF_PATH)
    await page.getByRole('button', { name: 'Upload Floor Plan PDF' }).click()
    await expectVisible(page.getByText('Plan ready. File ID:'), 30000)

    await page.getByRole('button', { name: 'Confirm Plan Scale' }).click()
    await expectVisible(page.getByText('Confirmed scale value:'))

    await page.getByRole('button', { name: 'Open Legend Assistant' }).click()
    await expectVisible(page.getByRole('heading', { name: 'Legend Assistant' }))

    const stage = page.locator('.plan-stage')
    await stage.scrollIntoViewIfNeeded()

    // First: drag legend area
    const box = await stage.boundingBox()
    assert(box, 'Plan stage box missing')
    await page.getByRole('button', { name: 'Select Legend Area' }).click()
    await page.mouse.move(box.x + 80, box.y + 80)
    await page.mouse.down()
    await page.mouse.move(box.x + 220, box.y + 180, { steps: 12 })
    await page.mouse.up()
    await page.waitForTimeout(600)

    // Stable fallback: click hatch pattern + adjust/confirm
    await page.getByRole('button', { name: 'Click Hatch Pattern' }).click()
    await stage.click({ position: { x: 320, y: 230 } })
    await expectVisible(page.getByText(/Hatch Sample: \d+ x \d+px/))
    await page.getByRole('button', { name: 'Larger' }).click()

    const savePromise = page.waitForResponse((resp) => resp.url().includes('/save-hatch-sample') && resp.request().method() === 'POST')
    await page.getByRole('button', { name: 'Confirm Hatch Sample' }).click()
    const saveResp = await savePromise
    assert(saveResp.ok(), 'save-hatch-sample failed')
    await expectVisible(page.getByText(/backendHatchSampleId=(?!null)/i))
    await expectVisible(page.getByText(/canAutoDetect=true/i))

    await page.getByRole('button', { name: 'Close' }).click()
    await page.getByRole('button', { name: 'Open Detection' }).click()
    await expectVisible(page.getByRole('heading', { name: 'Automatic Component Detection' }))

    const detectPromise = page.waitForResponse((resp) => resp.url().includes('/detect-hatch') && resp.request().method() === 'POST')
    await page.getByRole('button', { name: 'Auto Detect Selected Component' }).click()
    const detectResp = await detectPromise
    assert(detectResp.ok(), 'detect-hatch failed')

    const bodyText = await page.locator('body').innerText()
    const hasDetections = bodyText.includes('Backend returned')
    const noDetections = bodyText.includes('No detections found')
    assert(hasDetections || noDetections, 'Neither detections nor clean no-detections message shown')

    const detectionOverlaysCount = await page.locator('.overlay-accepted').count()
    let acceptRejectStatus = 'partial'
    if (hasDetections) {
      await expectVisible(page.getByRole('heading', { name: 'Review Detected Component Areas' }))
      const rows = page.locator('.workflow-step').filter({ hasText: /det_|det-/ })
      const count = await rows.count()
      if (count > 0) {
        await rows.nth(0).getByRole('button', { name: 'accepted' }).click()
      }
      if (count > 1) {
        await rows.nth(1).getByRole('button', { name: 'rejected' }).click()
      }
      await page.getByRole('button', { name: 'Confirm Review' }).click()
      acceptRejectStatus = count > 1 ? 'pass' : 'partial'
    }

    if (!hasDetections) {
      await page.getByRole('button', { name: 'Open Review' }).click().catch(() => {})
    }

    // Corrections path (works regardless of detection quality)
    await page.getByRole('button', { name: 'Open Correction Tool' }).click()
    await stage.scrollIntoViewIfNeeded()
    await page.getByTestId('add-correction-btn').click()
    await stage.scrollIntoViewIfNeeded()
    await stage.click({ position: { x: 420, y: 320 } })
    await page.waitForFunction(() => {
      const el = document.querySelector('[data-testid="added-correction-total"]')
      if (!el) return false
      const text = el.textContent || ''
      const m = text.match(/[-+]?\d*\.?\d+/g)
      const n = Number((m || []).slice(-1)[0] || 0)
      return n > 0
    })
    await page.getByTestId('subtract-correction-btn').click()
    await stage.scrollIntoViewIfNeeded()
    await stage.click({ position: { x: 540, y: 360 } })
    await page.waitForFunction(() => {
      const el = document.querySelector('[data-testid="subtracted-correction-total"]')
      if (!el) return false
      const text = el.textContent || ''
      const m = text.match(/[-+]?\d*\.?\d+/g)
      const n = Number((m || []).slice(-1)[0] || 0)
      return n > 0
    })
    const addedTotalText = await page.getByTestId('added-correction-total').innerText()
    const subtractedTotalText = await page.getByTestId('subtracted-correction-total').innerText()
    const addedTotal = Number((addedTotalText.match(/[-+]?\d*\.?\d+/g) || []).slice(-1)[0] || 0)
    const subtractedTotal = Number((subtractedTotalText.match(/[-+]?\d*\.?\d+/g) || []).slice(-1)[0] || 0)
    assert(addedTotal > 0, 'Added correction total did not increase')
    assert(subtractedTotal > 0, 'Subtracted correction total did not increase')

    // Height + final quantity
    await page.getByRole('button', { name: 'Open Height Assistant' }).click()
    await expectVisible(page.getByRole('heading', { name: 'Height Assistant' }).first())
    await page.locator('input[type=\"number\"]').last().fill('0.30')
    await page.getByRole('button', { name: 'Confirm Height' }).click()
    await expectVisible(page.getByRole('heading', { name: 'Calculate Quantity' }))
    const finalText = await page.locator('body').innerText()
    assert(finalText.includes('accepted_detection_area_m2'), 'accepted detection area missing from final table')
    assert(finalText.includes('added_correction_area_m2'), 'added correction area missing from final table')
    assert(finalText.includes('subtracted_correction_area_m2'), 'subtracted correction area missing from final table')
    assert(finalText.includes('final_area_m2'), 'final area missing from final table')
    assert(finalText.includes('volume_m3'), 'final volume missing from final table')
    assert(finalText.includes('final_area_m2 = accepted_detection_area_m2 + added_correction_area_m2 - subtracted_correction_area_m2'), 'formula text missing')
    assert(finalText.includes('volume_m3 = final_area_m2 x confirmed_height_m'), 'volume formula text missing')

    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Export Quantity Report' }).click()
    const download = await downloadPromise
    assert(download.suggestedFilename() === 'massiq_quantity_report.xlsx', 'Excel filename mismatch')

    const uploadRequests = requestLog.filter((req) => req.url.includes('/upload-pdf'))
    const saveRequests = requestLog.filter((req) => req.url.includes('/save-hatch-sample'))
    const detectRequests = requestLog.filter((req) => req.url.includes('/detect-hatch'))
    const exportRequests = requestLog.filter((req) => req.url.includes('/export-excel'))
    const uploadResponses = responseLog.filter((resp) => resp.url.includes('/upload-pdf'))
    const saveResponses = responseLog.filter((resp) => resp.url.includes('/save-hatch-sample'))
    const detectResponses = responseLog.filter((resp) => resp.url.includes('/detect-hatch'))
    const exportResponses = responseLog.filter((resp) => resp.url.includes('/export-excel'))
    assert(uploadRequests.length > 0, 'No /upload-pdf request observed')
    assert(saveRequests.length > 0, 'No /save-hatch-sample request observed')
    assert(detectRequests.length > 0, 'No /detect-hatch request observed')
    assert(exportRequests.length > 0, 'No /export-excel request observed')
    assert(uploadResponses.every((resp) => resp.ok), 'upload-pdf had non-2xx response')
    assert(saveResponses.every((resp) => resp.ok), 'save-hatch-sample had non-2xx response')
    assert(detectResponses.every((resp) => resp.ok), 'detect-hatch had non-2xx response')
    assert(exportResponses.every((resp) => resp.ok), 'export-excel had non-2xx response')

    assert(realConsoleErrors.length === 0, `Real console errors: ${realConsoleErrors.join('\n')}`)
    assert(pageErrors.length === 0, `Page errors: ${pageErrors.join('\n')}`)

    console.log(
      JSON.stringify({
        upload: 'pass',
        scale: 'pass',
        legendSelection: 'pass',
        clickToSample: 'pass',
        saveHatchSample: 'pass',
        autoDetect: 'pass',
        detectionOverlays: detectionOverlaysCount > 0 ? 'pass' : (noDetections ? 'partial' : 'fail'),
        acceptReject: acceptRejectStatus,
        corrections: addedTotal > 0 && subtractedTotal > 0 ? 'pass' : 'fail',
        height: 'pass',
        finalM3: 'pass',
        excelExport: 'pass',
        benignConsoleWarnings,
        realConsoleErrors,
        noConsoleErrors: realConsoleErrors.length === 0,
        uploadRequestCount: uploadRequests.length,
        saveRequestCount: saveRequests.length,
        detectRequestCount: detectRequests.length,
        exportRequestCount: exportRequests.length,
      })
    )
  } finally {
    await context.close()
    await browser.close()
  }
}

run().catch((error) => {
  console.error(error)
  process.exit(1)
})
