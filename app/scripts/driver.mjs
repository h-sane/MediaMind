// REPL driver for the MediaMind Electron desktop app (Windows).
// Designed for agents: wrap in a background shell, send commands on stdin,
// read stdout. Launches the *built* app (out/main/index.js) — run
// `npm run build` in app/ first if source changed since the last build.
//
// Lives inside app/ (not .claude/skills/run-desktop/) so Node's ESM
// bare-specifier resolution finds app/node_modules/playwright-core by
// walking up from this file's own location — see SKILL.md's Gotchas.
import { _electron as electron } from 'playwright-core'
import * as readline from 'node:readline'
import * as fs from 'node:fs'
import * as path from 'node:path'

const APP_DIR = path.resolve(import.meta.dirname, '..')
const SHOT_DIR = process.env.SCREENSHOT_DIR || path.join(APP_DIR, '.driver-shots')
fs.mkdirSync(SHOT_DIR, { recursive: true })

let app = null
let page = null

const electronBin = path.join(APP_DIR, 'node_modules/electron/dist/electron.exe')

const COMMANDS = {
  async launch() {
    if (app) return console.log('already launched')
    app = await electron.launch({
      executablePath: electronBin,
      args: [APP_DIR],
      timeout: 30_000
    })
    page = app.windows().find((w) => !w.url().startsWith('devtools://')) ?? (await app.firstWindow())
    await page.waitForLoadState('domcontentloaded')
    console.log('launched.', app.windows().length, 'windows:')
    for (const w of app.windows()) console.log(' ', w.url())
  },

  async ss(name) {
    if (!page) return console.log('ERROR: launch first')
    const f = path.join(SHOT_DIR, (name || `ss-${Date.now()}`) + '.png')
    await page.screenshot({ path: f })
    console.log('screenshot:', f)
  },

  async click(sel) {
    if (!page) return console.log('ERROR: launch first')
    const r = await page.evaluate((s) => {
      const el = document.querySelector(s)
      if (!el) return 'NOT_FOUND'
      el.click()
      return 'OK'
    }, sel)
    console.log('click', sel, '->', r)
  },

  async 'click-text'(text) {
    if (!page) return console.log('ERROR: launch first')
    const r = await page.evaluate((t) => {
      const els = [...document.querySelectorAll('button, a, [role="button"]')]
      const el = els.find((e) => e.textContent?.trim() === t) ?? els.find((e) => e.textContent?.includes(t))
      if (!el) return 'NOT_FOUND'
      el.click()
      return 'OK: ' + el.tagName
    }, text)
    console.log('click-text', JSON.stringify(text), '->', r)
  },

  // Explicit focus before typing — clicking a native <input> via DOM
  // .click() doesn't reliably move keyboard focus in this Electron/Chromium
  // context (buttons are fine; inputs aren't). Use this before `type` when
  // targeting a text input.
  async focus(sel) {
    if (!page) return console.log('ERROR: launch first')
    const r = await page.evaluate((s) => {
      const el = document.querySelector(s)
      if (!el) return 'NOT_FOUND'
      el.focus()
      return 'OK'
    }, sel)
    console.log('focus', sel, '->', r)
  },

  async type(text) {
    if (page) await page.keyboard.type(text, { delay: 30 })
  },
  async press(key) {
    if (page) await page.keyboard.press(key)
  },

  async wait(sel) {
    if (!page) return console.log('ERROR: launch first')
    try {
      await page.waitForSelector(sel, { timeout: 10_000 })
      console.log('found:', sel)
    } catch {
      console.log('TIMEOUT:', sel)
    }
  },

  async eval(expr) {
    if (!page) return console.log('ERROR: launch first')
    try {
      console.log(JSON.stringify(await page.evaluate(expr)))
    } catch (e) {
      console.log('ERROR:', e.message)
    }
  },

  async text(sel) {
    if (!page) return console.log('ERROR: launch first')
    console.log(
      await page.evaluate((s) => (s ? document.querySelector(s) : document.body)?.innerText ?? '(null)', sel || null)
    )
  },

  async sleep(ms) {
    await new Promise((r) => setTimeout(r, Number(ms) || 500))
  },

  async windows() {
    if (!app) return console.log('ERROR: launch first')
    for (const w of app.windows()) console.log(' ', w.url())
  },

  async quit() {
    if (app) await app.close().catch(() => {})
    app = null
    page = null
  },
  help() {
    console.log('commands:', Object.keys(COMMANDS).join(', '))
  }
}

const rl = readline.createInterface({ input: process.stdin, output: process.stdout, prompt: 'driver> ' })

// Commands run strictly sequentially: readline's 'line' handler is async,
// but readline itself does not wait for one handler's promise before firing
// the next line — a piped `<file` burst would otherwise start several
// commands concurrently (e.g. `press Enter` before `launch` finishes).
let queue = Promise.resolve()
let exited = false

function exitOnce() {
  if (exited) return
  exited = true
  process.exit(0)
}

rl.on('line', (line) => {
  queue = queue.then(async () => {
    const [cmd, ...rest] = line.trim().split(/\s+/)
    if (!cmd) return
    const fn = COMMANDS[cmd]
    if (!fn) {
      console.log('unknown:', cmd, '- try: help')
      return
    }
    try {
      await fn(rest.join(' '))
    } catch (e) {
      console.log('ERROR:', e.message)
    }
    if (cmd === 'quit') exitOnce()
  })
})
// With piped/redirected stdin (a `< file` or non-interactive `|`), 'close'
// fires as soon as every line has been *read*, not as soon as the async
// queue above has *finished* — each 'line' handler only chains a promise
// and returns immediately, so a fast EOF can fire 'close' while `launch`
// or a later command is still mid-flight. Await the queue before quitting.
rl.on('close', async () => {
  await queue
  if (!exited) await COMMANDS.quit()
  exitOnce()
})

console.log('MediaMind driver - "help" for commands, "launch" to start')
rl.prompt()
