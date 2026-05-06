import { useAuth } from '../composables/useAuth'

const API_BASE = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8001'

export class ApiError extends Error {
  constructor(message, status = 0, detail = '') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function apiRequest(path, options = {}) {
  const { state, clearSession } = useAuth()
  const hasFormData = options.body instanceof FormData
  const headers = {
    ...(hasFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers || {})
  }
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers
  })

  if (response.status === 401 && state.token) {
    clearSession()
  }

  if (!response.ok) {
    const contentType = response.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      const payload = await response.json()
      const detail = payload?.detail || payload?.message || JSON.stringify(payload)
      throw new ApiError(detail, response.status, detail)
    }
    const text = await response.text()
    throw new ApiError(text || `HTTP ${response.status}`, response.status, text)
  }

  if (response.status === 204) return null
  const contentType = response.headers.get('content-type') || ''
  return contentType.includes('application/json') ? response.json() : response.text()
}

export { API_BASE }
