import axios, { AxiosError } from "axios"

import type { ApiErrorPayload } from "./types"

const TOKEN_STORAGE_KEY = "ecommerce_ops_access_token"
export const AUTH_UNAUTHORIZED_EVENT = "ecommerce-ops:unauthorized"

export function getStoredToken(): string | null {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY)
}

export function storeToken(token: string): void {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function removeStoredToken(): void {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY)
}

export const http = axios.create({
  baseURL: "/api/v1",
  timeout: 20_000,
  headers: { "Content-Type": "application/json" },
})

http.interceptors.request.use((config) => {
  const token = getStoredToken()
  if (token) config.headers.set("Authorization", `Bearer ${token}`)
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorPayload>) => {
    const requestUrl = error.config?.url ?? ""
    if (error.response?.status === 401 && !requestUrl.endsWith("/auth/login")) {
      removeStoredToken()
      window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT))
    }
    return Promise.reject(error)
  },
)

export function getApiErrorMessage(error: unknown, fallback = "操作失败，请稍后重试"): string {
  if (axios.isAxiosError<ApiErrorPayload>(error)) {
    return error.response?.data?.message || error.message || fallback
  }
  return error instanceof Error ? error.message : fallback
}

