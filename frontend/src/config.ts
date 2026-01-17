// API Configuration - Force rebuild
const isLocalDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'

const envApiBaseRaw = import.meta.env.VITE_API_BASE_URL as string | undefined
const envWsBaseRaw = import.meta.env.VITE_WS_BASE_URL as string | undefined

const stripTrailingSlash = (value?: string) => (value ? value.replace(/\/+$/, '') : value)
const envApiBase = stripTrailingSlash(envApiBaseRaw)
const envWsBase = stripTrailingSlash(envWsBaseRaw)

export const API_BASE_URL = envApiBase
  ? envApiBase
  : isLocalDev
    ? 'http://localhost:8000'
    : 'https://ai-resume-critique-production.up.railway.app'

export const WS_BASE_URL = envWsBase
  ? envWsBase
  : isLocalDev
    ? 'ws://localhost:8000'
    : 'wss://ai-resume-critique-production.up.railway.app'
