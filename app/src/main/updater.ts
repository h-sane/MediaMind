import { app, BrowserWindow, ipcMain } from 'electron'
import { autoUpdater } from 'electron-updater'
import { logLine } from './log'
import { stopBackend } from './backend'

// In-app auto-update, GitHub-Releases backed (see electron-builder.yml
// `publish`). electron-updater compares the installed version against the
// latest published release, downloads the NSIS installer, and swaps it in on
// quit. We drive it manually rather than auto-downloading: the renderer shows
// a "new version available" bubble with an Update button (Explorer-style
// non-blocking notification), so the user is always the one who chooses to
// download and to restart-and-install. Nothing is ever installed silently.
//
// Only runs in a packaged build — electron-updater has no update feed under
// `npm run dev` and would throw. Guarded by app.isPackaged.

function broadcast(channel: string, payload: unknown): void {
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send(channel, payload)
  }
}

export function initUpdater(): void {
  if (!app.isPackaged) return

  // User initiates both the download and the install; nothing happens behind
  // their back. autoInstallOnAppQuit stays on so a downloaded update still
  // applies if they just close the app instead of clicking "Restart".
  autoUpdater.autoDownload = false
  autoUpdater.autoInstallOnAppQuit = true

  autoUpdater.on('update-available', (info) => {
    logLine('updater', `update available: ${info.version}`)
    broadcast('update:available', { version: info.version })
  })
  autoUpdater.on('download-progress', (p) => {
    broadcast('update:progress', { percent: Math.round(p.percent) })
  })
  autoUpdater.on('update-downloaded', (info) => {
    logLine('updater', `update downloaded: ${info.version}`)
    broadcast('update:downloaded', { version: info.version })
  })
  autoUpdater.on('error', (err) => {
    logLine('updater', `error: ${err instanceof Error ? err.message : String(err)}`)
    broadcast('update:error', { message: err instanceof Error ? err.message : String(err) })
  })

  ipcMain.handle('update:download', () => autoUpdater.downloadUpdate())
  // quitAndInstall closes every window and relaunches into the installer. Kill
  // the engine first and synchronously (stopBackend does a blocking taskkill on
  // Windows): the installer replaces files the still-running engine would
  // otherwise lock, causing "MediaMind cannot be closed". The installer's own
  // killEngine macro (build-resources/installer.nsh) is the backstop that also
  // covers updates arriving from older builds without this line.
  ipcMain.handle('update:install', () => {
    stopBackend()
    autoUpdater.quitAndInstall()
  })

  // Fire-and-forget: a check failure (offline, GitHub down) just means no
  // bubble appears — it must never block or crash startup.
  autoUpdater.checkForUpdates().catch((err) => {
    logLine('updater', `check failed: ${err instanceof Error ? err.message : String(err)}`)
  })
}
