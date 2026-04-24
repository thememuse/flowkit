import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electron', {
    /** Open the Google Flow browser window */
    openFlowTab: (options?: { focus?: boolean; reveal?: boolean }) => ipcRenderer.invoke('open-flow-tab', options),
    /** Basic app info from Electron main process */
    getAppInfo: () => ipcRenderer.invoke('get-app-info') as Promise<{ name: string; version: string }>,
    /** Stable machine id used for license activation */
    getMachineId: () => ipcRenderer.invoke('get-machine-id') as Promise<string>,
    /** Get/Set license API endpoint */
    getLicenseConfig: () => ipcRenderer.invoke('get-license-config') as Promise<{ apiBaseUrl: string }>,
    setLicenseConfig: (apiBaseUrl: string) => ipcRenderer.invoke('set-license-config', apiBaseUrl) as Promise<{ apiBaseUrl: string }>,
    /** Check current device license status */
    getLicenseStatus: (force = false) =>
        ipcRenderer.invoke('check-license', { force }) as Promise<{
            allowed: boolean
            status: 'ACTIVE' | 'EXPIRED' | 'REVOKED' | 'PENDING' | 'ERROR'
            machineId: string
            machineHash: string | null
            planCode: string | null
            planLabel: string | null
            activatedAt: string | null
            expiresAt: string | null
            revokedReason: string | null
            checkedAt: string
            serverTime: string | null
            source: 'remote' | 'cache'
            apiBaseUrl: string
            message: string
        }>,

    /** Get current health status from Python agent */
    getHealth: () => ipcRenderer.invoke('get-health'),

    /** Reconnect Chrome extension WebSocket to agent */
    reconnectExtension: () => ipcRenderer.invoke('reconnect-extension') as Promise<{ ok: boolean; method?: string; error?: string }>,

    /** Pick a local image file and return absolute path */
    pickImageFile: () => ipcRenderer.invoke('pick-image-file') as Promise<string | null>,
    /** Pick a local file by media kind */
    pickFile: (kind: 'image' | 'audio' | 'video' | 'any' = 'any') =>
        ipcRenderer.invoke('pick-file', kind) as Promise<string | null>,
    /** Pick a local directory path */
    pickDirectory: () => ipcRenderer.invoke('pick-directory') as Promise<string | null>,
    /** Reveal a file/folder path in OS shell */
    openPath: (targetPath: string) => ipcRenderer.invoke('open-path', targetPath) as Promise<{ ok: boolean; error?: string }>,

    /** Subscribe to agent sidecar status updates */
    onAgentStatus: (callback: (status: string) => void) => {
        const handler = (_event: Electron.IpcRendererEvent, status: string) => callback(status)
        ipcRenderer.on('agent-status', handler)
        return () => ipcRenderer.removeListener('agent-status', handler)
    },
    /** Subscribe to license status changes pushed by main process */
    onLicenseStatusChanged: (callback: (status: {
        allowed: boolean
        status: 'ACTIVE' | 'EXPIRED' | 'REVOKED' | 'PENDING' | 'ERROR'
        machineId: string
        machineHash: string | null
        planCode: string | null
        planLabel: string | null
        activatedAt: string | null
        expiresAt: string | null
        revokedReason: string | null
        checkedAt: string
        serverTime: string | null
        source: 'remote' | 'cache'
        apiBaseUrl: string
        message: string
    }) => void) => {
        const handler = (_event: Electron.IpcRendererEvent, status: {
            allowed: boolean
            status: 'ACTIVE' | 'EXPIRED' | 'REVOKED' | 'PENDING' | 'ERROR'
            machineId: string
            machineHash: string | null
            planCode: string | null
            planLabel: string | null
            activatedAt: string | null
            expiresAt: string | null
            revokedReason: string | null
            checkedAt: string
            serverTime: string | null
            source: 'remote' | 'cache'
            apiBaseUrl: string
            message: string
        }) => callback(status)
        ipcRenderer.on('license-status-changed', handler)
        return () => ipcRenderer.removeListener('license-status-changed', handler)
    },

    /** Platform info */
    platform: process.platform,

    /** Window controls */
    windowMinimize: () => ipcRenderer.invoke('window-minimize'),
    windowToggleMaximize: () => ipcRenderer.invoke('window-toggle-maximize'),
    windowClose: () => ipcRenderer.invoke('window-close'),
    isWindowMaximized: () => ipcRenderer.invoke('window-is-maximized') as Promise<boolean>,
})
