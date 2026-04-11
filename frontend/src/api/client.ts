/**
 * Shared axios instance for all API calls.
 * Base URL: VITE_API_BASE_URL env var (defaults to /api/v1 for same-origin proxy).
 */
import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// Inject offline flag into response metadata
apiClient.interceptors.response.use(
  response => response,
  error => {
    if (!navigator.onLine) {
      return Promise.reject({ ...error, offline: true })
    }
    return Promise.reject(error)
  }
)
