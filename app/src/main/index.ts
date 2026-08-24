import { app, shell, BrowserWindow, ipcMain, dialog, clipboard, screen, session } from 'electron'
import { existsSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { join } from 'node:path'
import { startBackend, stopBackend, getBackendInfo } from './backend'
import { initUpdater } from './updater'
import { logLine, logPath } from './log'
import { purge, readDataLocations } from './purge'
import type { DataLocation, PurgeResult, ShellOpenResult } from '../shared/types'

/** The central app-data store, matching the backend's `config.app_data_dir()`:
 * the `MEDIAMIND_DATA_DIR` override if set (used to isolate tests from real
 * app-data — see the backend), otherwise `%APPDATA%\MediaMind` (shared with
 * Electron's own userData). */
function centralDataDir(): string {
  return process.env.MEDIAMIND_DATA_DIR || join(app.getPath('appData'), 'MediaMind')
}

// ---------------------------------------------------------------------------
// Native "Open with" dialog (SHOpenWithDialog via COM), window-owned so it
// behaves as a proper modal instead of a floating orphan window — the same
// way real Explorer's own "Open with" dialog is parented to Explorer. Also
// sidesteps the fragile `rundll32.exe shell32.dll,OpenAs_RunDLLW <path>`
// hand-off (kept below only as a fallback): that entry point re-parses the
// path out of a raw command-line string it builds itself, rather than
// receiving it as a structured API parameter, which is a known source of
// corruption for some paths. `koffi` is a pure-npm FFI library (prebuilt
// binaries, no compiler toolchain) used only for this one COM call.
// ---------------------------------------------------------------------------

interface Win32Bridge {
  ensureCom: () => void
  openWith: (hwnd: unknown, path: string) => number
  toPointer: (buf: Buffer) => unknown
}

let win32: Win32Bridge | null = null
let win32LoadFailed = false

function loadWin32(): Win32Bridge | null {
  if (win32 || win32LoadFailed) return win32
  try {
    // require, not import: a missing/unsupported native binary must degrade
    // to the rundll32 fallback, not crash the app at startup.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const koffi = require('koffi')
    const shell32 = koffi.load('shell32.dll')
    const ole32 = koffi.load('ole32.dll')

    koffi.struct('OPENASINFO', {
      pcszFile: 'str16',
      pcszClass: 'str16',
      oaifInFlags: 'uint32'
    })

    const SHOpenWithDialog = shell32.func(
      'int32 __stdcall SHOpenWithDialog(void *hwndParent, _Inout_ OPENASINFO *poainfo)'
    )
    const CoInitializeEx = ole32.func(
      'int32 __stdcall CoInitializeEx(void *pvReserved, uint32 dwCoInit)'
    )

    let comReady = false
    win32 = {
      ensureCom: () => {
        if (comReady) return
        // HRESULT ignored on purpose: S_OK, S_FALSE (already initialized),
        // and RPC_E_CHANGED_MODE (Chromium already initialized this thread
        // in a different apartment) all mean COM is usable here.
        CoInitializeEx(null, 0x2 /* COINIT_APARTMENTTHREADED */)
        comReady = true
      },
      openWith: (hwnd, path) =>
        SHOpenWithDialog(hwnd, {
          pcszFile: path,
          pcszClass: null,
          oaifInFlags: 0x1 | 0x2 | 0x4 // OAIF_ALLOW_REGISTRATION | OAIF_REGISTER_EXT | OAIF_EXEC
        }),
      // Electron's getNativeWindowHandle() returns the HWND's raw bytes, not
      // a buffer we want the address of — koffi.as() reinterprets those
      // bytes as the pointer value itself.
      toPointer: (buf) => koffi.as(buf, 'void *')
    }
  } catch (err) {
    win32LoadFailed = true
    logLine('shell:open-with', `koffi unavailable, will use rundll32 fallback: ${err instanceof Error ? err.message : err}`)
  }
  return win32
}

const HRESULT_ERROR_CANCELLED = -2147023673 // HRESULT_FROM_WIN32(ERROR_CANCELLED)

// Deliberately synchronous: SHOpenWithDialog is modal and blocks until the
// user picks an app or cancels, same as Electron's own dialog.showOpenDialogSync
// — an accepted pattern for "wait on a modal OS dialog" IPC calls. It blocks
// only the main process's *other* IPC handlers for that span; the renderer's
// own data traffic (fs/dedupe/etc.) goes straight to the Python backend over
// HTTP/WS, bypassing the main process entirely, so browsing/progress bars are
// unaffected. Running it on koffi's async thread pool instead was considered
// and rejected: SHOpenWithDialog requires STA COM initialized on its exact
// calling thread, and koffi's pool doesn't guarantee CoInitializeEx and the
// dialog call land on the same OS thread — that would be a same-class bug to
// the one this change is fixing, just harder to notice.
function openWithNative(win: BrowserWindow, path: string): boolean {
  const bridge = loadWin32()
  if (!bridge) return false
  try {
    bridge.ensureCom()
    const hwnd = bridge.toPointer(win.getNativeWindowHandle())
    const hr = bridge.openWith(hwnd, path)
    if (hr >= 0) return true // succeeded — dialog was shown and handled
    if (hr === HRESULT_ERROR_CANCELLED) return true // user cancelled — not an error
    logLine('shell:open-with', `SHOpenWithDialog failed hr=0x${(hr >>> 0).toString(16)} path="${path}"`)
    return false
  } catch (err) {
    logLine('shell:open-with', `SHOpenWithDialog threw: ${err instanceof Error ? err.message : err}`)
    return false
  }
}

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 960,
    minHeight: 640,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#fafafa',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      // Chromium throttles timers, pauses rAF, and deprioritizes rendering
      // and media loading once the window is minimized or occluded — which
      // stalls thumbnail/image/video loading whenever MediaMind is in the
      // background. This is a working file manager, not a battery-sipping tab;
      // keep it running at full speed when it doesn't have focus.
      backgroundThrottling: false
    }
  })

  win.on('ready-to-show', () => win.show())

  // Windows leaves an invisible ~8px resize border around thick-frame windows
  // that Chromium doesn't subtract when it maximizes: `maximize()` lands the
  // window 16px wider/taller than the monitor's work area, offset -8/-8, so
  // it spills a strip under the taskbar and past the screen edge.
  //
  // Windows also refuses any `setBounds()` while the WS_MAXIMIZE style bit
  // is set — it silently re-snaps to its own (wrong) computed rect on every
  // attempt, at any delay, so the bounds can't be corrected in place. The
  // only way to land on the right size is to drop the native maximized
  // state and size the window ourselves ("fake maximize"), which then
  // leaves `isMaximized()` false and breaks the OS maximize button's normal
  // click-to-restore toggle. `fakeMaximized` below re-implements that
  // toggle: a second maximize click while already fake-maximized restores
  // the last normal size instead of re-filling the screen.
  let fakeMaximized = false
  let adjustingBounds = false
  let lastNormalBounds = win.getBounds()

  win.on('resize', () => {
    if (adjustingBounds) return
    if (fakeMaximized) {
      // Re-clicking maximize while fake-maximized makes Windows run its own
      // (buggy, oversized) maximize sequence again before our 'maximize'
      // handler below gets to convert it into a restore — that transient
      // resize also lands here first. Only treat this as a genuine manual
      // drag-resize-away-from-fullscreen if the OS isn't mid-maximize.
      if (win.isMaximized()) return
      fakeMaximized = false
      lastNormalBounds = win.getBounds()
      return
    }
    if (!win.isMaximized()) lastNormalBounds = win.getBounds()
  })

  // Every maximize click — fill or restore — arrives here with the OS
  // genuinely in WS_MAXIMIZE (it thought the window was restored, so the
  // click sent a real SC_MAXIMIZE), so both branches need the same
  // unmaximize-then-settle dance before a setBounds() will stick.
  function settleBoundsAfterMaximize(target: Electron.Rectangle, becomesFakeMaximized: boolean): void {
    adjustingBounds = true
    setTimeout(() => {
      win.unmaximize()
      setTimeout(() => {
        win.setBounds(target)
        fakeMaximized = becomesFakeMaximized
        adjustingBounds = false
      }, 100)
    }, 50)
  }

  win.on('maximize', () => {
    if (fakeMaximized) {
      settleBoundsAfterMaximize(lastNormalBounds, false)
      return
    }
    const workArea = screen.getDisplayMatching(win.getBounds()).workArea
    settleBoundsAfterMaximize(workArea, true)
  })

  // External links open in the OS browser, never inside the app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  // Window-level shortcuts that belong to the OS window itself (new window,
  // fullscreen), not to the Explorer content the renderer's own
  // useKeyboardShortcuts.ts binds — handled here so they work regardless of
  // renderer focus state.
  win.webContents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown') return
    if (input.control && !input.shift && !input.alt && input.key.toLowerCase() === 'n') {
      event.preventDefault()
      createWindow()
    } else if (input.key === 'F11') {
      event.preventDefault()
      win.setFullScreen(!win.isFullScreen())
    }
  })

  if (!app.isPackaged && process.env.ELECTRON_RENDERER_URL) {
    win.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'))
  }
  return win
}

/** Builds a Windows `CF_HDROP` clipboard payload (the format Explorer itself
 * writes on Ctrl+C) so files copied in MediaMind can be pasted into a real
 * Explorer window or any other CF_HDROP-aware app. Layout: a 20-byte
 * DROPFILES header (pFiles offset, an unused POINT, fNC, fWide) followed by
 * a double-null-terminated list of null-terminated UTF-16LE paths. */
function buildCfHdrop(paths: string[]): Buffer {
  const header = Buffer.alloc(20)
  header.writeUInt32LE(20, 0) // pFiles: offset of the file list from struct start
  header.writeUInt32LE(1, 16) // fWide: file list is UTF-16LE
  const fileList = Buffer.from(paths.join('\0') + '\0\0', 'ucs2')
  return Buffer.concat([header, fileList])
}

function registerIpc(): void {
  ipcMain.handle('backend:info', () => getBackendInfo())

  // Lets the renderer gate dev-only UI (the in-app log console) so it has
  // zero footprint in a packaged build regardless of the renderer-side
  // feature flag also being left on.
  ipcMain.handle('app:is-packaged', () => app.isPackaged)

  ipcMain.handle('dialog:pick-folder', async () => {
    const result = await dialog.showOpenDialog({
      title: 'Choose a folder for MediaMind to manage',
      properties: ['openDirectory']
    })
    return result.canceled ? null : result.filePaths[0]
  })

  // Pure shell hand-offs: none of these move/copy/delete anything MediaMind
  // manages, so the manifest/dry-run/count-check safety rules don't apply.
  // The one required guard is validating the path exists before handing it
  // to the shell or a child process.
  ipcMain.handle('shell:reveal', (_event, path: string): boolean => {
    if (!existsSync(path)) return false
    shell.showItemInFolder(path)
    return true
  })

  ipcMain.handle('shell:open-path', async (_event, path: string): Promise<ShellOpenResult> => {
    if (!existsSync(path)) return 'Path does not exist'
    const error = await shell.openPath(path)
    return error || null
  })

  ipcMain.handle('shell:open-with', (event, path: string): boolean => {
    if (!existsSync(path) || process.platform !== 'win32') return false
    logLine('shell:open-with', `invoke path="${path}" len=${path.length}`)

    const win = BrowserWindow.fromWebContents(event.sender)
    if (win && openWithNative(win, path)) return true

    // Fallback: the wide-char `OpenAs_RunDLLW` entry point, not the ANSI
    // `OpenAs_RunDLL` one — on current Windows builds the ANSI entry point
    // spawns a dead rundll32 host with no visible window (verified: ~16 MB,
    // no top-level window at all), while the W variant launches the real
    // modern picker (`OpenWith.exe`, ~140 MB) that Explorer itself uses.
    // Unlike the SHOpenWithDialog path above, this spawns a detached,
    // parentless process — kept only as a safety net so "Open with" never
    // fully breaks (e.g. koffi's native binary missing on this machine).
    logLine('shell:open-with', 'fallback -> rundll32 OpenAs_RunDLLW')
    spawn('rundll32.exe', ['shell32.dll,OpenAs_RunDLLW', path], { detached: true, stdio: 'ignore' }).unref()
    return true
  })

  // Opens the real, OS-owned Recycle Bin window — the "Recent deletions"
  // panel (Phase P item 4) hands restoration off to this trusted native UI
  // rather than attempting a programmatic restore-by-path itself (see
  // `core/oplog.py::list_deletions`'s docstring for why). `shell:` is a
  // virtual namespace path Explorer resolves, not a real filesystem path,
  // so this goes through `explorer.exe` directly rather than `shell.openPath`.
  ipcMain.handle('shell:open-recycle-bin', (): boolean => {
    if (process.platform !== 'win32') return false
    spawn('explorer.exe', ['shell:RecycleBinFolder'], { detached: true, stdio: 'ignore' }).unref()
    return true
  })

  ipcMain.handle('clipboard:copy-path', (_event, paths: string[]): void => {
    clipboard.writeText(paths.map((p) => `"${p}"`).join('\n'))
  })

  ipcMain.handle('clipboard:write-files', (_event, paths: string[]): boolean => {
    if (process.platform !== 'win32') return false
    clipboard.writeBuffer('CF_HDROP', buildCfHdrop(paths))
    return true
  })

  // "Send to > Desktop (create shortcut)" needs the real Desktop path —
  // only resolvable in the main process (Electron's `app.getPath`).
  ipcMain.handle('paths:desktop', (): string => app.getPath('desktop'))

  // What "Remove all MediaMind data" would delete, with per-drive reachability.
  ipcMain.handle('appdata:locations', (): DataLocation[] => readDataLocations(centralDataDir()))

  // Delete every library's `.mediamind/` on a connected drive plus the central
  // app-data store. Stops the backend first so its file handles (models, logs,
  // sqlite) are released — the wipe then can't fail on a lock. If any library's
  // drive is offline and `skipUnreachable` is false, `purge` deletes nothing
  // and reports them so the caller can connect-and-retry or skip.
  ipcMain.handle('appdata:purge', (_event, skipUnreachable: boolean): PurgeResult => {
    const locs = readDataLocations(centralDataDir())
    const hasUnreachable = locs.some((l) => l.kind === 'library' && !l.reachable)
    if (hasUnreachable && !skipUnreachable) return purge(centralDataDir(), false)

    stopBackend() // release the engine's file handles before deleting them
    const result = purge(centralDataDir(), skipUnreachable)
    logLine('appdata:purge', `deleted ${result.deleted.length}, failed ${result.failed.length}`)
    return result
  })

  // Restart the whole app after a purge, back to a clean first-run state. A
  // full relaunch (not a backend-only restart) sidesteps stale port/token
  // reconnection — the backend was just killed and its data wiped.
  ipcMain.handle('app:relaunch', (): void => {
    app.relaunch()
    app.exit(0)
  })

  // Fire-and-forget error reports from the renderer (fetch failures, unhandled
  // exceptions, render crashes) so they land in the same persistent log as
  // the engine's own output instead of only a transient devtools console.
  ipcMain.on('renderer:log-error', (_event, entry: { source: string; message: string }) => {
    console.error(`[renderer] ${entry.source}: ${entry.message}`)
    logLine(`renderer:${entry.source}`, entry.message)
  })
}

app.whenReady().then(async () => {
  console.log(`[main] log file: ${logPath()}`)
  logLine('main', 'app ready')
  registerIpc()

  // Plain <img>/<video>/<audio> tags can't set request headers, so the
  // renderer streams media straight from the backend with no auth header
  // attached. Inject it here at the session layer for every request to the
  // backend's origin instead.
  session.defaultSession.webRequest.onBeforeSendHeaders((details, callback) => {
    const token = getBackendInfo()?.token
    if (token && new URL(details.url).hostname === '127.0.0.1') {
      details.requestHeaders['X-MediaMind-Token'] = token
    }
    callback({ requestHeaders: details.requestHeaders })
  })

  const win = createWindow()

  win.webContents.on('render-process-gone', (_event, details) => {
    console.error('[main] renderer process gone:', details)
    logLine('main', `renderer process gone: ${JSON.stringify(details)}`)
  })

  try {
    await startBackend()
    win.webContents.send('backend:ready', getBackendInfo())
  } catch (err) {
    console.error('Failed to start engine:', err)
    logLine('main', `failed to start engine: ${err instanceof Error ? err.stack ?? err.message : err}`)
    dialog.showErrorBox(
      'MediaMind engine failed to start',
      `${err instanceof Error ? err.message : err}\n\n` +
        'Check that Python and the mediamind package are available ' +
        '(see backend/README.md).'
    )
  }

  // Check for an app update in the background once the window is up (no-op in
  // dev / unpackaged builds). Non-blocking: the renderer shows a bubble if one
  // is found.
  initUpdater()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  stopBackend()
  app.quit()
})

app.on('before-quit', () => {
  stopBackend()
})
