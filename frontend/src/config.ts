// API Configuration
const isLocalDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'

export const API_BASE_URL = isLocalDev
  ? 'http://localhost:8000'
  : 'https://ai-resume-critique-production.up.railway.app'

export const WS_BASE_URL = isLocalDev
  ? 'ws://localhost:8000'
  : 'wss://ai-resume-critique-production.up.railway.app'
