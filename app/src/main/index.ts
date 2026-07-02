import { app, shell, BrowserWindow, ipcMain, dialog } from 'electron'
import { join } from 'node:path'
import { startBackend, stopBackend, getBackendInfo } from './backend'

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

  if (!app.isPackaged && process.env.ELECTRON_RENDERER_URL) {
    win.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'))
  }
  return win
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
}

app.whenReady().then(async () => {
  registerIpc()
  const win = createWindow()

  try {
    await startBackend()
    win.webContents.send('backend:ready', getBackendInfo())
  } catch (err) {
    console.error('Failed to start engine:', err)
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
