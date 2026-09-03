/**
 * HAJIMI Desktop — Electron 主进程入口（M0 骨架）
 *
 * 原则（对齐重构计划）：
 *  - 渲染层零网络权限：对 :8011 Sidecar 的 HTTP/SSE 全部收敛在主进程（M1 接入）。
 *  - contextIsolation: true / nodeIntegration: false / sandbox: true。
 *  - 纯逻辑（可 vitest）放 desktop/core/，此文件只做 Electron 接线。
 */
import { app, BrowserWindow, ipcMain, Menu, nativeImage, shell, Tray } from 'electron'
import { join } from 'node:path'
import { clampWindowSize } from '../core/window'
import { configFromEnv } from '../core/config'
import { SidecarClient } from './services/sidecarClient'
import { SidecarManager, type SidecarState } from './services/sidecarManager'
import { TaskRunner } from './services/taskRunner'
import { loadConsent, saveConsent } from './services/consentStore'

const cfg = configFromEnv()
const client = new SidecarClient(cfg)

let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let isQuitting = false
let consentState = { accepted: false }

const manager = new SidecarManager(
  client,
  cfg,
  // repoRoot = desktop/ 的上级（开发态 app.getAppPath()=desktop）
  join(app.getAppPath(), '..'),
  (s: SidecarState) => {
    mainWindow?.webContents.send('sidecar:state', s)
  }
)

const runner = new TaskRunner(
  client,
  cfg,
  () => mainWindow,
  () => consentState.accepted,
  (dontShowAgain: boolean) => {
    consentState.accepted = true
    if (dontShowAgain) saveConsent(true)
  }
)

// 与 PyQt 端 MainWidget 默认面板尺寸同量级的起点；M2/M3 引入窗口状态记忆后由 store 驱动
const DEFAULT_SIZE = clampWindowSize(380, 620, { minW: 280, minH: 52 })

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: DEFAULT_SIZE.w,
    height: DEFAULT_SIZE.h,
    minWidth: DEFAULT_SIZE.minW,
    minHeight: DEFAULT_SIZE.minH,
    frame: false,
    show: false,
    backgroundColor: '#0f172a',
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true
    }
  })

  mainWindow.once('ready-to-show', () => mainWindow?.show())

  // 关闭 → 隐藏到托盘；真正退出走托盘菜单 quit（isQuitting 闸门）
  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault()
      mainWindow?.hide()
    }
  })
  mainWindow.on('closed', () => {
    mainWindow = null
  })

  // 外链一律走系统浏览器，禁止窗口内导航逃逸
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url)
    return { action: 'deny' }
  })

  if (process.env['ELECTRON_RENDERER_URL']) {
    void mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    void mainWindow.loadFile(join(__dirname, '../dist/index.html'))
  }
}

function createTray(iconPath: string): void {
  try {
    const image = nativeImage.createFromPath(iconPath)
    tray = new Tray(image.isEmpty() ? nativeImage.createEmpty() : image)
    tray.setToolTip('HAJIMI 桌面助手')
    tray.setContextMenu(
      Menu.buildFromTemplate([
        {
          label: '显示 / 隐藏主窗',
          click: () => {
            if (!mainWindow) createWindow()
            else if (mainWindow.isVisible()) mainWindow.hide()
            else {
              mainWindow.show()
              mainWindow.focus()
            }
          }
        },
        { type: 'separator' },
        {
          label: '退出',
          click: () => {
            isQuitting = true
            app.quit()
          }
        }
      ])
    )
    tray.on('double-click', () => {
      if (!mainWindow) createWindow()
      else {
        mainWindow.show()
        mainWindow.focus()
      }
    })
  } catch {
    // 托盘失败不阻断主窗（无显示环境的 Linux 冒烟等）
    tray = null
  }
}

function registerIpc(): void {
  ipcMain.handle('app:get-version', () => app.getVersion())

  ipcMain.handle(
    'task:submit',
    async (
      _e,
      arg: { query: string; acceptConsent: boolean; dontShowAgain?: boolean }
    ) => {
      const query = String(arg?.query ?? '').trim()
      if (!query) return { ok: false, error: '指令为空' }
      // 对齐 execute_task 的 _ensure_l5_ready：提交前确保 Sidecar 可用（必要时拉起）
      const ready = await manager.ensureRunning()
      if (!ready.ok) return { ok: false, error: ready.reason }
      return runner.submit(query, Boolean(arg?.acceptConsent), arg?.dontShowAgain !== false)
    }
  )

  ipcMain.handle('task:cancel', async () => runner.cancel())

  ipcMain.handle('sidecar:status', async () => {
    const live = await client.healthLive()
    const ok = !!live && (live.status === 'ok' || live.status === 'degraded')
    return { ok, detail: live ? String(live.status ?? 'ok') : 'down' }
  })

  ipcMain.handle('consent:accepted', () => consentState.accepted)
}

// ── 单实例锁：二次启动聚焦已有窗口 ──
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (!mainWindow.isVisible()) mainWindow.show()
      mainWindow.focus()
    }
  })

  void app.whenReady().then(() => {
    consentState = { accepted: loadConsent().l5_consent_accepted }
    registerIpc()
    createWindow()
    createTray(join(__dirname, '../build/icon.png'))

    // 启动链对齐 PyQt main「自动拉起 Sidecar」：非阻塞探活/拉起，状态推给渲染层
    void manager.ensureRunning().catch(() => undefined)

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow()
    })
  })
}

app.on('before-quit', () => {
  isQuitting = true
  runner.abortLocal()
  if (cfg.stopServicesOnExit) manager.shutdown()
  tray?.destroy()
  tray = null
})

// Windows/Linux 下主窗关闭即隐藏到托盘，因此不监听 window-all-closed 退出；
// 退出由托盘菜单驱动 isQuitting → app.quit()。
