import { app, shell, BrowserWindow, ipcMain, dialog, clipboard } from 'electron'
import { existsSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { join } from 'node:path'
import { startBackend, stopBackend, getBackendInfo } from './backend'
import { logLine, logPath } from './log'
import type { ShellOpenResult } from '../shared/types'

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
      sandbox: false
    }
  })

  win.on('ready-to-show', () => win.show())

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

  ipcMain.handle('shell:open-with', (_event, path: string): boolean => {
    if (!existsSync(path) || process.platform !== 'win32') return false
    // Invokes the native "Open with" chooser dialog — same DLL entry point
    // Explorer itself uses; no custom app-picker UI needed.
    spawn('rundll32.exe', ['shell32.dll,OpenAs_RunDLL', path], { detached: true, stdio: 'ignore' }).unref()
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
