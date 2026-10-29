import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { resolveBackendApiUrl, setBackendApiUrl } from './runtimeConfig'

export const api = axios.create({
  baseURL: resolveBackendApiUrl(),
  timeout: 30000,
})

// Request interceptor
api.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore()
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const authStore = useAuthStore()

    if (error.response) {
      const { status, data } = error.response

      // Handle 401 Unauthorized
      if (status === 401 && authStore.token) {
        try {
          await authStore.refreshAccessToken()
          // Retry the original request
          return api.request(error.config)
        } catch {
          authStore.logout()
          window.location.href = '/login'
        }
      }

      // Show error message
      const detail = data?.detail
      const message = (typeof detail === 'string' ? detail : detail?.message)
        || (Array.isArray(detail) ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join('; ') : '')
        || data?.error
        || data?.message
        || 'An error occurred'
      ElMessage.error(message)

      return Promise.reject(error)
    }

    // Network error
    ElMessage.error('Network error. Please check your connection.')
    return Promise.reject(error)
  }
)

export function updateBackendApiUrl(value: string) {
  const normalized = setBackendApiUrl(value)
  api.defaults.baseURL = normalized
  return normalized
}

export default api
