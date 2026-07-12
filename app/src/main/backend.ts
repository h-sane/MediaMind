/**
 * Backend (Python engine) lifecycle: spawn, discover port, health-check, stop.
 *
 * The engine binds 127.0.0.1 on a free port and prints `MEDIAMIND_PORT=<port>`
 * on stdout. A per-session random token is passed via MEDIAMIND_TOKEN and
 * required on every request — no other local process can drive the engine.
 */
import { spawn, ChildProcess } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { app } from 'electron'
import { logLine } from './log'

export interface BackendInfo {
  port: number
  token: string
}

const HEALTH_TIMEOUT_MS = 30_000

let child: ChildProcess | null = null
let info: BackendInfo | null = null

function engineCommand(): { cmd: string; args: string[] } {
  if (app.isPackaged) {
    // In a packaged build, the PyInstaller bundle is extracted to
    // resources/engine/ by electron-builder extraResources.
    const { join } = require('node:path')
    const engineExe = process.platform === 'win32' ? 'mediamind.exe' : 'mediamind'
    const enginePath = join(process.resourcesPath, 'engine', engineExe)
    return { cmd: enginePath, args: [] }
  }
  // Dev: use the venv Python from .env or the environment.
  const python =
    import.meta.env.MAIN_VITE_PYTHON || process.env.MEDIAMIND_PYTHON || 'python'
  return { cmd: python, args: ['-m', 'mediamind'] }
}

function waitForPort(proc: ChildProcess): Promise<number> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error('Backend did not report a port in time')),
      HEALTH_TIMEOUT_MS
    )
    let buffer = ''
    proc.stdout!.on('data', (chunk: Buffer) => {
      logLine('engine:stdout', chunk.toString())
      buffer += chunk.toString()
      const match = buffer.match(/MEDIAMIND_PORT=(\d+)/)
      if (match) {
        clearTimeout(timer)
        resolve(Number(match[1]))
      }
    })
    proc.on('error', (err) => {
      clearTimeout(timer)
      reject(new Error(`Failed to start backend process: ${err.message}`))
    })
    proc.on('exit', (code) => {
      clearTimeout(timer)
      reject(new Error(`Backend exited early (code ${code})`))
    })
  })
}

async function waitForHealth(port: number, token: string): Promise<void> {
  const deadline = Date.now() + HEALTH_TIMEOUT_MS
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/v1/health`, {
        headers: { 'X-MediaMind-Token': token }
      })
      if (res.ok) return
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error('Backend health check timed out')
}

export async function startBackend(): Promise<BackendInfo> {
  if (info) return info
  const token = randomBytes(32).toString('hex')
  const { cmd, args } = engineCommand()

  const proc = spawn(cmd, args, {
    env: { ...process.env, MEDIAMIND_TOKEN: token },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true
  })
  proc.stderr!.on('data', (chunk: Buffer) => {
    console.log(`[engine] ${chunk.toString().trimEnd()}`)
    logLine('engine:stderr', chunk.toString())
  })
  child = proc

  const port = await waitForPort(proc)
  await waitForHealth(port, token)
  info = { port, token }
  console.log(`[engine] ready on 127.0.0.1:${port}`)
  logLine('main', `engine ready on 127.0.0.1:${port}`)

  // Monitor post-startup exit so we don't silently lose the engine.
  proc.on('exit', (code, signal) => {
    if (info) {
      console.error(`[engine] exited unexpectedly (code=${code} signal=${signal})`)
      logLine('main', `engine exited unexpectedly (code=${code} signal=${signal})`)
      info = null
      child = null
    }
  })

  return info
}

export function getBackendInfo(): BackendInfo | null {
  return info
}

export function stopBackend(): void {
  if (child && !child.killed) {
    child.kill()
  }
  child = null
  info = null
}
