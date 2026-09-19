import { defineStore } from "pinia"
import { computed, ref } from "vue"

import * as authApi from "../api/auth"
import { getStoredToken, removeStoredToken, storeToken } from "../api/http"
import type { Permission, User, UserRole } from "../types/domain"

const ROLE_PERMISSIONS: Record<UserRole, ReadonlySet<Permission>> = {
  admin: new Set<Permission>([
    "user.manage",
    "store.manage",
    "product.write",
    "inventory.write",
    "competitor.write",
    "ai.generate",
    "job.operate",
    "asset.review",
    "ad.confirm",
    "experiment.write",
    "performance.write",
    "settings.manage",
  ]),
  operator: new Set<Permission>([
    "store.manage",
    "product.write",
    "inventory.write",
    "competitor.write",
    "ai.generate",
    "job.operate",
    "asset.review",
    "ad.confirm",
    "experiment.write",
    "performance.write",
  ]),
  viewer: new Set<Permission>(),
}

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(getStoredToken())
  const user = ref<User | null>(null)
  const initialized = ref(false)
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value && user.value))
  const role = computed<UserRole | null>(() => user.value?.role ?? null)

  function can(permission: Permission): boolean {
    return role.value ? ROLE_PERMISSIONS[role.value].has(permission) : false
  }

  function clearSession(): void {
    removeStoredToken()
    token.value = null
    user.value = null
    initialized.value = true
  }

  async function signIn(payload: authApi.LoginPayload): Promise<void> {
    loading.value = true
    try {
      const tokenResponse = await authApi.login(payload)
      storeToken(tokenResponse.access_token)
      token.value = tokenResponse.access_token
      user.value = await authApi.getCurrentUser()
      initialized.value = true
    } catch (error) {
      clearSession()
      throw error
    } finally {
      loading.value = false
    }
  }

  async function restoreSession(): Promise<void> {
    if (initialized.value) return
    const storedToken = getStoredToken()
    if (!storedToken) {
      clearSession()
      return
    }
    token.value = storedToken
    try {
      user.value = await authApi.getCurrentUser()
    } catch {
      clearSession()
    } finally {
      initialized.value = true
    }
  }

  async function signOut(): Promise<void> {
    try {
      if (token.value) await authApi.logout()
    } finally {
      clearSession()
    }
  }

  return {
    token,
    user,
    initialized,
    loading,
    isAuthenticated,
    role,
    can,
    clearSession,
    signIn,
    signOut,
    restoreSession,
  }
})

