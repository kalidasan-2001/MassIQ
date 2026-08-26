// Cross-platform launcher for the E2E backend (Playwright's webServer
// spawns this via `node`, not a shell script, so there is no bash/cmd
// syntax divergence between local Windows dev and CI's ubuntu-latest).
//
// Picks the backend's venv Python if one exists (local dev, where
// dependencies live in backend/.venv/), otherwise falls back to `python`
// on PATH (CI, where the existing backend CI job installs dependencies
// directly via `pip install -r requirements.txt`, no venv).
const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')

const BACKEND_DIR = path.resolve(__dirname, '..', '..', '..', 'backend')
const PORT = process.env.E2E_BACKEND_PORT || '8020'

function resolvePythonExecutable() {
  const candidates =
    process.platform === 'win32'
      ? [path.join(BACKEND_DIR, '.venv', 'Scripts', 'python.exe')]
      : [path.join(BACKEND_DIR, '.venv', 'bin', 'python')]
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate
  }
  return 'python'
}

const python = resolvePythonExecutable()
console.log(`[start-backend] using interpreter: ${python}`)

const child = spawn(python, ['scripts/e2e_server.py', '--port', PORT], {
  cwd: BACKEND_DIR,
  stdio: 'inherit',
  env: process.env,
})

child.on('exit', (code) => process.exit(code ?? 0))
process.on('SIGTERM', () => child.kill('SIGTERM'))
process.on('SIGINT', () => child.kill('SIGINT'))
