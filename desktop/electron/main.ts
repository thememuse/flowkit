import { app, BrowserView, BrowserWindow, dialog, ipcMain, Tray, Menu, nativeImage, shell, session } from 'electron'
import { join } from 'path'
import { sidecar } from './sidecar'
import { checkLicense, DEFAULT_LICENSE_API_BASE, getMachineId, loadLicenseConfig, saveLicenseConfig, type LicenseCheckResult } from './license'

let mainWindow: BrowserWindow | null = null
let flowWindow: BrowserWindow | null = null
let flowSidebarView: BrowserView | null = null
let tray: Tray | null = null
let flowExtensionId: string | null = null
let appQuitting = false
let licenseEnforceTimer: ReturnType<typeof setInterval> | null = null
let licenseEnforceInFlight = false
let licenseRevokedLockdown = false
let licenseRevokedNotified = false

// Ensure unique app identity in dev mode to avoid collisions with generic Electron apps.
app.setName('FlowKit')
app.setPath('userData', join(app.getPath('appData'), 'FlowKit'))

const gotSingleInstanceLock = app.requestSingleInstanceLock()
if (!gotSingleInstanceLock) {
    app.quit()
    process.exit(0)
}

const ICON_PATH = join(__dirname, '../../resources/icon.png')
const EXTENSION_PATH = join(process.resourcesPath ?? join(__dirname, '../../..'), 'extension')
const FLOW_URL = 'https://labs.google/fx/tools/flow'
const FLOW_SIDEBAR_RATIO = 0.30
const FLOW_SIDEBAR_MIN = 320
const FLOW_SIDEBAR_MAX = 460
const LICENSE_CONFIG_PATH = join(app.getPath('userData'), 'license-config.json')
const LICENSE_CACHE_PATH = join(app.getPath('userData'), 'license-cache.json')
const DEFAULT_LICENSE_API = process.env.FLOWKIT_LICENSE_API_BASE ?? DEFAULT_LICENSE_API_BASE
const LICENSE_REVOKE_POLL_MS = 5000

let lastLicenseCheck: LicenseCheckResult | null = null

// In dev mode, use local extension path
const extensionPath = app.isPackaged
    ? EXTENSION_PATH
    : join(__dirname, '../../../extension')

async function loadExtension() {
    try {
        // Patch declarativeNetRequest — use webRequest to inject Referer header instead
        session.defaultSession.webRequest.onBeforeSendHeaders(
            { urls: ['https://aisandbox-pa.googleapis.com/*'] },
            (details, callback) => {
                const headers = { ...details.requestHeaders }
                headers['Referer'] = 'https://labs.google/'
                callback({ requestHeaders: headers })
            }
        )

        // Use new API (Electron 36+), fall back to deprecated for older builds
        const extHost = (session.defaultSession as any).extensions ?? session.defaultSession
        const loaded = await extHost.loadExtension(extensionPath, { allowFileAccess: true })
        flowExtensionId = (loaded as any)?.id ?? null
        console.log('[main] Extension loaded from:', extensionPath, 'id:', flowExtensionId ?? 'unknown')
    } catch (err) {
        console.error('[main] Failed to load extension:', err)
    }
}

function calcFlowSidebarWidth(totalWidth: number): number {
    const byRatio = Math.floor(totalWidth * FLOW_SIDEBAR_RATIO)
    return Math.max(FLOW_SIDEBAR_MIN, Math.min(FLOW_SIDEBAR_MAX, byRatio))
}

function layoutFlowViews() {
    if (!flowWindow || flowWindow.isDestroyed()) return
    const [totalWidth, totalHeight] = flowWindow.getContentSize()
    const sidebarWidth = flowSidebarView ? calcFlowSidebarWidth(totalWidth) : 0

    if (flowSidebarView) {
        flowSidebarView.setBounds({ x: Math.max(0, totalWidth - sidebarWidth), y: 0, width: sidebarWidth, height: totalHeight })
        flowSidebarView.setAutoResize({ height: true })
    }
}


function createMainWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 800,
        minWidth: 900,
        minHeight: 600,
        titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
        backgroundColor: '#eef3fb',
        show: false,
        webPreferences: {
            preload: join(__dirname, '../preload/preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
        }
    })

    // Load renderer
    if (process.env.ELECTRON_RENDERER_URL) {
        mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
    } else {
        // electron-vite outputs renderer assets to out/renderer in preview/production
        mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
    }

    mainWindow.once('ready-to-show', () => {
        mainWindow?.show()
        mainWindow?.focus()
    })

    // Safety net: ensure dashboard is visible even if ready-to-show is delayed.
    setTimeout(() => {
        if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.isVisible()) {
            console.warn('[main] Forcing main window show after startup timeout')
            mainWindow.show()
            mainWindow.focus()
        }
    }, 2500)

    mainWindow.webContents.on('did-finish-load', () => {
        console.log('[main] Main window renderer loaded:', mainWindow?.webContents.getURL())
    })

    mainWindow.webContents.on('did-fail-load', (_e, code, desc, url) => {
        console.error('[main] Main window failed to load:', { code, desc, url })
    })

    mainWindow.on('closed', () => {
        mainWindow = null
    })
}

function createFlowWindow(opts: { focusOnShow?: boolean; revealOnReady?: boolean } = {}) {
    console.log('[main] Creating Flow window')
    const focusOnShow = opts.focusOnShow === true
    const revealOnReady = opts.revealOnReady !== false
    flowWindow = new BrowserWindow({
        width: 1420,
        height: 900,
        minWidth: 1080,
        minHeight: 680,
        title: 'Google Flow',
        backgroundColor: '#0a0f1f',
        show: false,
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            session: session.defaultSession,
        }
    })

    flowWindow.loadURL(FLOW_URL).catch((err) => {
        console.error('[main] Failed to load Flow URL:', err)
    })
    flowWindow.webContents.on('did-finish-load', () => {
        console.log('[main] Flow content loaded:', flowWindow?.webContents.getURL())
    })
    flowWindow.webContents.on('did-fail-load', (_e, code, desc, url) => {
        console.error('[main] Flow content failed:', { code, desc, url })
    })
    flowWindow.webContents.setWindowOpenHandler(({ url }) => {
        void shell.openExternal(url)
        return { action: 'deny' }
    })
    flowWindow.once('ready-to-show', () => {
        if (!flowWindow || flowWindow.isDestroyed() || !revealOnReady) return
        if (focusOnShow) {
            flowWindow.show()
            flowWindow.focus()
            return
        }
        if (typeof flowWindow.showInactive === 'function') flowWindow.showInactive()
        else flowWindow.show()
        if (mainWindow && !mainWindow.isDestroyed()) mainWindow.focus()
    })

    if (flowExtensionId) {
        flowSidebarView = new BrowserView({
            webPreferences: {
                contextIsolation: true,
                nodeIntegration: false,
                session: session.defaultSession,
            }
        })
        flowWindow.addBrowserView(flowSidebarView)
        const sidePanelUrl = `chrome-extension://${flowExtensionId}/side_panel.html`
        flowSidebarView.webContents.loadURL(sidePanelUrl).catch((err) => {
            console.error('[main] Failed to load extension sidebar:', err)
        })
        flowSidebarView.webContents.on('did-finish-load', () => {
            console.log('[main] Flow sidebar loaded:', flowSidebarView?.webContents.getURL())
        })
        flowSidebarView.webContents.on('did-fail-load', (_e, code, desc, url) => {
            console.error('[main] Flow sidebar failed:', { code, desc, url })
        })
    } else {
        flowSidebarView = null
        console.warn('[main] Flow extension ID unavailable — sidebar disabled in Flow window')
    }

    layoutFlowViews()
    flowWindow.on('resize', layoutFlowViews)
    flowWindow.on('maximize', layoutFlowViews)
    flowWindow.on('unmaximize', layoutFlowViews)
    flowWindow.on('enter-full-screen', layoutFlowViews)
    flowWindow.on('leave-full-screen', layoutFlowViews)

    flowWindow.on('close', (event) => {
        if (appQuitting) return
        // Keep Flow session alive for token/captcha; hide instead of destroying.
        event.preventDefault()
        flowWindow?.hide()
    })

    flowWindow.on('closed', () => {
        flowSidebarView = null
        flowWindow = null
    })
}

function createTray() {
    try {
        const rawIcon = nativeImage.createFromPath(ICON_PATH)
        if (rawIcon.isEmpty()) {
            console.warn('[main] Tray icon is invalid/empty, skipping tray creation:', ICON_PATH)
            return
        }

        const icon = rawIcon.resize({ width: 16, height: 16 })
        tray = new Tray(icon)
        tray.setToolTip('FlowKit')
    } catch (err) {
        console.error('[main] Failed to create tray, continue without tray:', err)
        tray = null
        return
    }

    const updateMenu = (agentStatus: string) => {
        const menu = Menu.buildFromTemplate([
            { label: `FlowKit — ${agentStatus}`, enabled: false },
            { type: 'separator' },
            { label: 'Open Dashboard', click: () => { mainWindow?.show(); mainWindow?.focus() } },
            { label: 'Open Google Flow', click: () => openFlowWindow({ focus: true, reveal: true }) },
            { type: 'separator' },
            { label: 'Quit', click: () => app.quit() }
        ])
        tray?.setContextMenu(menu)
    }

    updateMenu('Starting...')

    // Update tray when agent status changes
    sidecar.on('status', (status: string) => updateMenu(status))

    tray.on('click', () => {
        mainWindow?.show()
        mainWindow?.focus()
    })
}

function openFlowWindow(options: { focus?: boolean; reveal?: boolean } = {}) {
    console.log('[main] openFlowWindow invoked')
    const focus = options.focus === true
    const reveal = options.reveal !== false
    if (flowWindow && !flowWindow.isDestroyed()) {
        if (!reveal) return
        if (!flowWindow.isVisible()) {
            if (!focus && typeof flowWindow.showInactive === 'function') flowWindow.showInactive()
            else flowWindow.show()
        }
        if (focus) flowWindow.focus()
        else if (mainWindow && !mainWindow.isDestroyed()) mainWindow.focus()
    } else {
        createFlowWindow({ focusOnShow: focus, revealOnReady: reveal })
    }
}

function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms))
}

async function waitForWebContentsReady(webContents: Electron.WebContents | null | undefined, timeoutMs = 8000): Promise<boolean> {
    if (!webContents || webContents.isDestroyed()) return false
    if (!webContents.isLoadingMainFrame()) return true
    return await new Promise<boolean>((resolve) => {
        let settled = false
        const finish = (ok: boolean) => {
            if (settled) return
            settled = true
            clearTimeout(timer)
            try { webContents.removeListener('did-finish-load', onFinish) } catch { }
            try { webContents.removeListener('did-fail-load', onFail) } catch { }
            resolve(ok)
        }
        const onFinish = () => finish(true)
        const onFail = () => finish(false)
        const timer = setTimeout(() => finish(!webContents.isLoadingMainFrame()), timeoutMs)
        webContents.once('did-finish-load', onFinish)
        webContents.once('did-fail-load', onFail)
    })
}

async function waitForExtensionConnected(timeoutMs = 12000): Promise<boolean> {
    const start = Date.now()
    while (Date.now() - start < timeoutMs) {
        try {
            const res = await fetch('http://127.0.0.1:8100/health', { signal: AbortSignal.timeout(1500) })
            if (res.ok) {
                const health = await res.json() as { extension_connected?: boolean }
                if (Boolean(health?.extension_connected)) return true
            }
        } catch {
            // retry
        }
        await sleep(500)
    }
    return false
}

async function requestExtensionReconnectViaSidebar(): Promise<boolean> {
    if (!flowSidebarView || flowSidebarView.webContents.isDestroyed()) return false
    const ready = await waitForWebContentsReady(flowSidebarView.webContents, 6000)
    if (!ready) return false
    try {
        const viaSidePanel = await flowSidebarView.webContents.executeJavaScript(`
            new Promise((resolve) => {
                try {
                    chrome.runtime.sendMessage({ type: 'RECONNECT' }, (resp) => {
                        const err = chrome.runtime.lastError;
                        if (err) {
                            resolve({ ok: false, error: err.message || 'runtime_send_failed' });
                            return;
                        }
                        resolve({ ok: !!(resp && resp.ok), raw: resp || null });
                    });
                } catch (e) {
                    resolve({ ok: false, error: e?.message || String(e) });
                }
            });
        `, true) as { ok?: boolean; error?: string } | undefined
        return Boolean(viaSidePanel?.ok)
    } catch (err) {
        console.warn('[main] reconnect via side-panel failed:', err)
        return false
    }
}

async function getLicenseConfig() {
    return loadLicenseConfig(LICENSE_CONFIG_PATH, DEFAULT_LICENSE_API)
}

async function performLicenseCheck(force = false): Promise<LicenseCheckResult> {
    if (!force && lastLicenseCheck) {
        const elapsed = Date.now() - new Date(lastLicenseCheck.checkedAt).getTime()
        if (elapsed < 5000) {
            return lastLicenseCheck
        }
    }

    const machineId = await getMachineId()
    const config = await getLicenseConfig()
    const result = await checkLicense({
        apiBaseUrl: config.apiBaseUrl,
        machineId,
        cachePath: LICENSE_CACHE_PATH,
        appVersion: app.getVersion(),
        platform: process.platform,
    })
    lastLicenseCheck = result
    return result
}

function stopLicenseEnforcer() {
    if (licenseEnforceTimer) {
        clearInterval(licenseEnforceTimer)
        licenseEnforceTimer = null
    }
}

function pushLicenseStatusToRenderer(result: LicenseCheckResult) {
    mainWindow?.webContents.send('license-status-changed', result)
}

async function enforceLicenseRevocation(source: 'startup' | 'poll'): Promise<void> {
    if (licenseEnforceInFlight) return
    licenseEnforceInFlight = true
    try {
        const result = await performLicenseCheck(true)
        pushLicenseStatusToRenderer(result)

        if (result.status === 'REVOKED') {
            if (!licenseRevokedLockdown) {
                console.error('[license] Device revoked. Locking app until re-activated.', {
                    source,
                    machineId: result.machineId,
                    reason: result.revokedReason ?? null,
                })
            }
            licenseRevokedLockdown = true
            sidecar.stop()

            if (!licenseRevokedNotified) {
                licenseRevokedNotified = true
                const reasonLine = result.revokedReason
                    ? `\nLý do: ${result.revokedReason}`
                    : ''
                void dialog.showMessageBox(mainWindow ?? undefined, {
                    type: 'warning',
                    title: 'FlowKit license đã bị thu hồi (REVOKED)',
                    message: `Thiết bị này không còn quyền sử dụng FlowKit.${reasonLine}`,
                    detail: 'Ứng dụng vẫn mở để bạn sao chép Machine ID và yêu cầu admin Active lại.',
                    buttons: ['Đã hiểu'],
                    defaultId: 0,
                })
            }
            return
        }

        if (licenseRevokedLockdown) {
            console.log('[license] Device re-activated. Resuming sidecar.')
            licenseRevokedLockdown = false
            sidecar.start()
        }
        licenseRevokedNotified = false
    } catch (err) {
        console.error('[license] Revoke enforcement check failed:', err)
    } finally {
        licenseEnforceInFlight = false
    }
}

function startLicenseEnforcer() {
    if (licenseEnforceTimer) return
    void enforceLicenseRevocation('startup')
    licenseEnforceTimer = setInterval(() => {
        void enforceLicenseRevocation('poll')
    }, LICENSE_REVOKE_POLL_MS)
}

// ─── IPC Handlers ────────────────────────────────────────────

ipcMain.handle('open-flow-tab', (_event, payload?: { focus?: boolean; reveal?: boolean }) => openFlowWindow({
    focus: payload?.focus,
    reveal: payload?.reveal,
}))
ipcMain.handle('get-app-info', () => ({
    name: app.getName(),
    version: app.getVersion(),
}))
ipcMain.handle('get-health', async () => {
    try {
        const res = await fetch('http://127.0.0.1:8100/health')
        return res.json()
    } catch {
        return { status: 'error', extension_connected: false }
    }
})
ipcMain.handle('get-machine-id', async () => getMachineId())
ipcMain.handle('get-license-config', async () => getLicenseConfig())
ipcMain.handle('set-license-config', async (_event, apiBaseUrl: string) => {
    const config = await saveLicenseConfig(LICENSE_CONFIG_PATH, apiBaseUrl, DEFAULT_LICENSE_API)
    lastLicenseCheck = null
    return config
})
ipcMain.handle('check-license', async (_event, payload?: { force?: boolean }) => {
    const result = await performLicenseCheck(Boolean(payload?.force))
    pushLicenseStatusToRenderer(result)
    return result
})
ipcMain.handle('pick-image-file', async () => {
    const result = await dialog.showOpenDialog(mainWindow ?? undefined, {
        properties: ['openFile'],
        filters: [
            { name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp'] },
            { name: 'All Files', extensions: ['*'] },
        ],
    })
    if (result.canceled || result.filePaths.length === 0) return null
    return result.filePaths[0]
})
ipcMain.handle('pick-file', async (_event, kind: 'image' | 'audio' | 'video' | 'any' = 'any') => {
    const filters = kind === 'image'
        ? [
            { name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp'] },
            { name: 'All Files', extensions: ['*'] },
        ]
        : kind === 'audio'
            ? [
                { name: 'Audio', extensions: ['wav', 'mp3', 'm4a', 'aac', 'flac', 'ogg'] },
                { name: 'All Files', extensions: ['*'] },
            ]
            : kind === 'video'
                ? [
                    { name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm'] },
                    { name: 'All Files', extensions: ['*'] },
                ]
                : [{ name: 'All Files', extensions: ['*'] }]
    const result = await dialog.showOpenDialog(mainWindow ?? undefined, {
        properties: ['openFile'],
        filters,
    })
    if (result.canceled || result.filePaths.length === 0) return null
    return result.filePaths[0]
})
ipcMain.handle('pick-directory', async () => {
    const result = await dialog.showOpenDialog(mainWindow ?? undefined, {
        properties: ['openDirectory', 'createDirectory'],
    })
    if (result.canceled || result.filePaths.length === 0) return null
    return result.filePaths[0]
})
ipcMain.handle('open-path', async (_event, targetPath: string) => {
    if (!targetPath) return { ok: false, error: 'Path is required' }
    const error = await shell.openPath(targetPath)
    if (error) return { ok: false, error }
    return { ok: true }
})
ipcMain.handle('window-minimize', () => {
    if (!mainWindow || mainWindow.isDestroyed()) return
    mainWindow.minimize()
})
ipcMain.handle('window-toggle-maximize', () => {
    if (!mainWindow || mainWindow.isDestroyed()) return false
    if (mainWindow.isMaximized()) mainWindow.unmaximize()
    else mainWindow.maximize()
    return mainWindow.isMaximized()
})
ipcMain.handle('window-close', () => {
    if (!mainWindow || mainWindow.isDestroyed()) return
    mainWindow.close()
})
ipcMain.handle('window-is-maximized', () => {
    if (!mainWindow || mainWindow.isDestroyed()) return false
    return mainWindow.isMaximized()
})

ipcMain.on('agent-ready', () => {
    // Forward to renderer
    mainWindow?.webContents.send('agent-status', 'ready')
})

ipcMain.handle('reconnect-extension', async () => {
    try {
        // Ensure Flow window (and extension side panel) is alive.
        openFlowWindow({ focus: false, reveal: false })
        await waitForWebContentsReady(flowSidebarView?.webContents, 6000)
        await waitForWebContentsReady(flowWindow?.webContents, 6000)

        for (let i = 0; i < 3; i += 1) {
            const sent = await requestExtensionReconnectViaSidebar()
            if (sent) {
                const connected = await waitForExtensionConnected(3500)
                if (connected) return { ok: true, method: 'runtimeMessage' }
            }
            await sleep(600)
        }

        // Find the extension background service worker webContents
        const allContents = (session.defaultSession as any).getAllWebContents?.()
            ?? require('electron').webContents.getAllWebContents()
        const bgContents = allContents.find((wc: Electron.WebContents) => {
            const url = wc.getURL?.() ?? ''
            return flowExtensionId
                ? url.includes(`chrome-extension://${flowExtensionId}`) && url.includes('background')
                : url.startsWith('chrome-extension://') && url.includes('background')
        })
        if (bgContents && !bgContents.isDestroyed()) {
            try {
                await bgContents.executeJavaScript(`
                    try {
                        manualDisconnect = false;
                        connectToAgent();
                    } catch(e) {}
                `)
                const connected = await waitForExtensionConnected(4500)
                if (connected) return { ok: true, method: 'executeJavaScript' }
            } catch (err) {
                console.warn('[main] reconnect via background worker failed:', err)
            }
        }

        // Fallback: reload extension via session
        if (flowExtensionId) {
            const extHost = (session.defaultSession as any).extensions ?? session.defaultSession
            if (typeof extHost.reloadExtension === 'function') {
                await extHost.reloadExtension(flowExtensionId)
                // Ensure side panel points to the latest extension runtime.
                if (flowSidebarView && !flowSidebarView.webContents.isDestroyed()) {
                    const sidePanelUrl = `chrome-extension://${flowExtensionId}/side_panel.html`
                    await flowSidebarView.webContents.loadURL(sidePanelUrl)
                    await waitForWebContentsReady(flowSidebarView.webContents, 6000)
                }
                const sent = await requestExtensionReconnectViaSidebar()
                const connected = sent ? await waitForExtensionConnected(5000) : false
                if (connected) return { ok: true, method: 'reloadExtension' }
            }
        }
        return { ok: false, error: 'Extension vẫn OFF sau nhiều lần reconnect' }
    } catch (e: any) {
        return { ok: false, error: e?.message ?? String(e) }
    }
})

// ─── App Lifecycle ───────────────────────────────────────────

app.whenReady().then(async () => {
    // Send status while loading
    await loadExtension()
    createMainWindow()
    createTray()
    // Keep Flow window available for captcha/token flows.
    try {
        openFlowWindow({ focus: false, reveal: false })
    } catch (err) {
        console.error('[main] Failed to auto-open Flow window:', err)
    }

    startLicenseEnforcer()

    // Start Python sidecar
    sidecar.start()

    sidecar.on('status', (status: string) => {
        mainWindow?.webContents.send('agent-status', status)
    })
})

app.on('second-instance', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
        if (mainWindow.isMinimized()) mainWindow.restore()
        mainWindow.show()
        mainWindow.focus()
    } else {
        createMainWindow()
    }
})

app.on('render-process-gone', (_event, webContents, details) => {
    console.error('[main] render-process-gone:', {
        reason: details.reason,
        exitCode: details.exitCode,
        url: webContents.getURL(),
    })
})

app.on('child-process-gone', (_event, details) => {
    console.error('[main] child-process-gone:', details)
})

app.on('window-all-closed', () => {
    // Keep running in tray
    if (process.platform !== 'darwin') {
        // On Windows, only quit when tray is exited
    }
})

app.on('before-quit', () => {
    appQuitting = true
    stopLicenseEnforcer()
    sidecar.stop()
})

app.on('activate', () => {
    if (!mainWindow) createMainWindow()
    else {
        mainWindow.show()
        mainWindow.focus()
    }
})
