// Console-error and network-failure monitoring shared by every spec.
//
// Policy (documented in docs/testing/BROWSER_E2E_STRATEGY.md):
//   - Any `console.error` or uncaught page exception fails the test unless
//     its text matches an entry in ALLOWLISTED_CONSOLE_PATTERNS below --
//     every allowlisted pattern must have a comment explaining why it's
//     harmless. Never suppress console errors globally.
//   - Any HTTP 5xx response from the backend fails the test. 4xx responses
//     are allowed by default (many are expected, e.g. 404s the app
//     handles) -- explicit negative-path tests assert on the exact 4xx
//     they expect separately; this monitor only ever fails on 5xx.

// Each entry: { pattern: RegExp, reason: 'why this is safe to ignore' }
const ALLOWLISTED_CONSOLE_PATTERNS = [
  {
    pattern: /Download the React DevTools/i,
    reason: 'React dev-mode informational message, not an error condition.',
  },
  {
    pattern: /not wrapped in act\(\.\.\.\)/i,
    reason:
      'Known cosmetic React 18 + @testing-library/user-event interaction warning ' +
      '(documented in docs/releases/R3_LEGEND_WORKFLOW_CHECKLIST.md) -- does not ' +
      'indicate a real defect; every assertion around it still passes.',
  },
  {
    pattern: /Failed to load resource: the server responded with a status of 4\d\d/i,
    reason:
      'Chromium itself logs a console.error for ANY non-2xx XHR/fetch response, ' +
      'independent of whether application code handled it -- this is the browser ' +
      'echoing the network layer, not evidence of an application bug. Genuine 5xx ' +
      'server failures are still caught separately by the network-failure monitor ' +
      '(assertClean() fails on any 5xx regardless of this allowlist), and each ' +
      'negative-path test asserts the app shows a controlled, visible error for the ' +
      'expected 4xx -- so a real regression (the app failing to handle a 4xx) still ' +
      'fails the test via those explicit UI assertions, just not via this console check.',
  },
]

function isAllowlisted(text) {
  return ALLOWLISTED_CONSOLE_PATTERNS.some(({ pattern }) => pattern.test(text))
}

/**
 * Attaches console/network/pageerror listeners to `page` and returns a
 * handle exposing `.errors` (unexpected console errors + page exceptions)
 * and `.failedRequests` (5xx responses seen so far). Call `.assertClean()`
 * at the end of a test (or rely on afterEach in a fixture) to fail loudly
 * with full diagnostic detail rather than a silent pass.
 */
function attachMonitoring(page) {
  const errors = []
  const failedRequests = []

  page.on('console', (msg) => {
    if (msg.type() !== 'error') return
    const text = msg.text()
    if (isAllowlisted(text)) return
    errors.push(`[console.error] ${text}`)
  })

  page.on('pageerror', (err) => {
    errors.push(`[uncaught exception] ${err.message}`)
  })

  page.on('response', (response) => {
    const status = response.status()
    if (status >= 500) {
      failedRequests.push({
        method: response.request().method(),
        url: response.url(),
        status,
      })
    }
  })

  return {
    errors,
    failedRequests,
    assertClean() {
      if (errors.length > 0) {
        throw new Error(`Unexpected browser console errors:\n${errors.join('\n')}`)
      }
      if (failedRequests.length > 0) {
        const summary = failedRequests
          .map((r) => `${r.method} ${new URL(r.url).pathname} -> ${r.status}`)
          .join('\n')
        throw new Error(`Unexpected 5xx API responses:\n${summary}`)
      }
    },
  }
}

module.exports = { attachMonitoring, ALLOWLISTED_CONSOLE_PATTERNS }
