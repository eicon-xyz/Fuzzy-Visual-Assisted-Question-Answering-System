/**
 * HAJIMI Desktop — Electron 主进程入口（M0 骨架）
 *
 * 原则（对齐重构计划）：
 *  - 渲染层零网络权限：对 :8011 Sidecar 的 HTTP/SSE 全部收敛在主进程（M1 接入）。
 *  - contextIsolation: true / nodeIntegration: false / sandbox: true。
 *  - 纯逻辑（可 vitest）放 desktop/core/，此文件只做 Electron 接线。
 */
import { app, BrowserWindow, globalShortcut, ipcMain, Menu, nativeImage, screen, shell, Tray } from 'electron'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { clampWindowSize } from '../core/window'
import { sanitizeWindowState, type WindowState } from '../core/windowState'
import { configFromEnv } from '../core/config'
import { resolveL5Root } from '../core/l5root'
import { SidecarClient } from './services/sidecarClient'
import { SidecarManager, type SidecarState } from './services/sidecarManager'
import { TaskRunner } from './services/taskRunner'
import { SettingsStore, type UserSettings } from './services/settingsStore'
import { AuthSession } from './services/authSession'

const cfg = configFromEnv()
const client = new SidecarClient(cfg)

let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let isQuitting = false

const manager = new SidecarManager(
  client,
  cfg,
  // repoRoot = desktop/ 的上级（开发态 app.getAppPath()=desktop）
  join(app.getAppPath(), '..'),
  (s: SidecarState) => {
    mainWindow?.webContents.send('sidecar:state', s)
  }
)

const settings = new SettingsStore(cfg, () => manager, () => {
  const root = resolveL5Root(
    { envOverride: cfg.l5RootOverride, repoRoot: join(app.getAppPath(), '..') },
    existsSync
  )
  return root ? join(root, 'server', '.env') : null
})

const auth = new AuthSession(cfg)

const runner = new TaskRunner(
  client,
  cfg,
  () => mainWindow,
  () => settings.consentAccepted(),
  (dontShowAgain: boolean) => settings.markConsent(dontShowAgain)
)

// 与 PyQt 端 MainWidget 默认面板尺寸同量级的起点
const DEFAULT_SIZE = clampWindowSize(380, 620, { minW: 280, minH: 52 })

// ── M3 窗口状态持久化（userData/window-state.json）──
function windowStatePath(): string {
  return join(app.getPath('userData'), 'hajimi-desktop', 'window-state.json')
}

function loadWindowState(): WindowState | null {
  try {
    const raw = JSON.parse(readFileSync(windowStatePath(), 'utf-8')) as WindowState
    const display = screen.getPrimaryDisplay().workArea
    return sanitizeWindowState(raw, { width: display.width + display.x, height: display.height + display.y })
  } catch {
    return null
  }
}

let saveTimer: NodeJS.Timeout | null = null
function scheduleSaveWindow(win: BrowserWindow): void {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    try {
      const b = win.getBounds()
      mkdirSync(join(app.getPath('userData'), 'hajimi-desktop'), { recursive: true })
      writeFileSync(
        windowStatePath(),
        JSON.stringify({ x: b.x, y: b.y, w: b.width, h: b.height, compact: compactMode }),
        'utf-8'
      )
    } catch {
      /* 状态保存失败不阻断 */
    }
  }, 400)
}

let compactMode = false

function applyCompact(win: BrowserWindow, compact: boolean): void {
  compactMode = compact
  const b = win.getBounds()
  if (compact) {
    win.setBounds({ x: b.x, y: b.y, width: b.width, height: 64 }, true)
  } else {
    win.setBounds({ x: b.x, y: b.y, width: Math.max(b.width, 380), height: 620 }, true)
  }
  win.webContents.send('window:mode', { compact })
  scheduleSaveWindow(win)
}

// ── M3 全局停止快捷键（默认关，设置开；PyQt 无实现，属新增对齐）──
function applyStopShortcut(enabled: boolean): void {
  try {
    globalShortcut.unregisterAll()
    if (enabled) {
      globalShortcut.register('CommandOrControl+Alt+J', () => {
        void runner.cancel()
      })
    }
  } catch {
    /* 无显示/被占用环境下静默 */
  }
}

function createWindow(): void {
  const st = loadWindowState()
  mainWindow = new BrowserWindow({
    x: st?.x,
    y: st?.y,
    width: st?.w ?? DEFAULT_SIZE.w,
    height: st?.h ?? DEFAULT_SIZE.h,
    minWidth: DEFAULT_SIZE.minW,
    minHeight: DEFAULT_SIZE.minH,
    frame: false,
    show: false,
    backgroundColor: '#0f172a',
    webPreferences: {
      // electron-vite 输出 ESM（out/main/main.mjs / out/preload/preload.mjs）；
      // sandboxed preload 不支持 ESM，故 sandbox:false——contextIsolation 仍开启，
      // preload 仅暴露白名单桥，安全边界不变。
      preload: join(import.meta.dirname, '../preload/preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      webSecurity: true
    }
  })

  const win = mainWindow
  mainWindow.once('ready-to-show', () => {
    win.show()
    if (st?.compact) applyCompact(win, true)
  })
  win.on('move', () => scheduleSaveWindow(win))
  win.on('resize', () => scheduleSaveWindow(win))

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
    // electron-vite 产物布局：out/main / out/preload / out/renderer
    void mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
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

  ipcMain.handle('consent:accepted', () => settings.consentAccepted())

  // ── M2 设置 / 账号 ──
  ipcMain.handle('settings:get', () => settings.load())

  ipcMain.handle('settings:save', async (_e, fragment: UserSettings) => {
    const r = settings.saveFragment(fragment ?? {})
    if (r.ok) {
      applyStopShortcut(fragment?.global_stop_enabled === true)
      // 对齐 PyQt：保存模型设置后重启 Sidecar 使其生效（尽力而为，不阻断保存结果）
      try {
        await settings.restartSidecar()
      } catch {
        /* 重启失败下次探活自愈 */
      }
    }
    return r
  })

  ipcMain.handle('auth:status', () => ({
    valid: cfg.skipLogin || auth.isValid(),
    username: auth.username()
  }))

  ipcMain.handle('auth:login', async (_e, arg: { username: string; password: string }) => {
    try {
      await auth.login(String(arg?.username ?? ''), String(arg?.password ?? ''))
      return { ok: true }
    } catch (err) {
      return { ok: false, error: (err as Error).message }
    }
  })

  ipcMain.handle('auth:logout', () => {
    auth.logout()
    return { ok: true }
  })

  // ── M3 窗口模式 / 全局快捷键 ──
  ipcMain.handle('window:set-compact', (_e, compact: boolean) => {
    if (mainWindow) applyCompact(mainWindow, Boolean(compact))
    return { ok: true, compact: compactMode }
  })

  ipcMain.handle('window:get-mode', () => ({ compact: compactMode }))
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
    registerIpc()
    createWindow()
    createTray(join(__dirname, '../../build/icon.png'))
    applyStopShortcut(settings.load().global_stop_enabled === true)

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
  try {
    globalShortcut.unregisterAll()
  } catch {
    /* ignore */
  }
  tray?.destroy()
  tray = null
})

// Windows/Linux 下主窗关闭即隐藏到托盘，因此不监听 window-all-closed 退出；
// 退出由托盘菜单驱动 isQuitting → app.quit()。
