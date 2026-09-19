import type { EntityStatus, InventoryAdviceRun, PlatformAccount, Store, StorePlatform, StoreSummary } from "../types/domain"
import { http } from "./http"
import type { PageResponse } from "./types"

export interface StoreQuery {
  page: number
  page_size: number
  q?: string
  platform?: StorePlatform
  status?: EntityStatus
}

export interface StorePayload {
  store_name: string
  platform: StorePlatform
  external_store_id?: string | null
  owner_user_id?: number | null
  status: EntityStatus
  remark?: string | null
}

export async function getStores(params: StoreQuery): Promise<PageResponse<Store>> {
  return (await http.get<PageResponse<Store>>("/stores", { params })).data
}
export async function getStore(id: number): Promise<Store> {
  return (await http.get<Store>(`/stores/${id}`)).data
}
export async function getStoreSummary(id: number): Promise<StoreSummary> {
  return (await http.get<StoreSummary>(`/stores/${id}/summary`)).data
}
export async function createStore(payload: StorePayload): Promise<Store> {
  return (await http.post<Store>("/stores", payload)).data
}
export async function updateStore(id: number, payload: Partial<StorePayload>): Promise<Store> {
  return (await http.patch<Store>(`/stores/${id}`, payload)).data
}

export async function getPlatformAccounts(storeId: number): Promise<PlatformAccount[]> {
  return (await http.get<PlatformAccount[]>(`/stores/${storeId}/platform-accounts`)).data
}
export async function createPlatformAccount(storeId: number, payload: { account_name: string; remark?: string | null }): Promise<PlatformAccount> {
  return (await http.post<PlatformAccount>(`/stores/${storeId}/platform-accounts`, payload)).data
}
export async function updatePlatformAccount(id: number, payload: { account_name?: string; remark?: string | null }): Promise<PlatformAccount> {
  return (await http.patch<PlatformAccount>(`/platform-accounts/${id}`, payload)).data
}
export async function startPlatformAuthorization(id: number): Promise<void> {
  await http.post(`/platform-accounts/${id}/authorization/start`)
}
export async function revokePlatformAuthorization(id: number): Promise<void> {
  await http.post(`/platform-accounts/${id}/authorization/revoke`)
}

export interface AdviceGeneratePayload {
  lookback_days: number
  coverage_days: number
  safety_multiplier: number
  min_outbound_events: number
}
export async function getLatestInventoryAdvice(storeId: number): Promise<InventoryAdviceRun> {
  return (await http.get<InventoryAdviceRun>(`/stores/${storeId}/inventory-advice`)).data
}
export async function generateInventoryAdvice(storeId: number, payload: AdviceGeneratePayload): Promise<InventoryAdviceRun> {
  return (await http.post<InventoryAdviceRun>(`/stores/${storeId}/inventory-advice/generate`, payload)).data
}
export async function getInventoryAdviceRuns(storeId: number, page = 1, pageSize = 20): Promise<PageResponse<Omit<InventoryAdviceRun, "items">>> {
  return (await http.get<PageResponse<Omit<InventoryAdviceRun, "items">>>(`/stores/${storeId}/inventory-advice/runs`, { params: { page, page_size: pageSize } })).data
}
export async function getInventoryAdviceRun(storeId: number, runId: number): Promise<InventoryAdviceRun> {
  return (await http.get<InventoryAdviceRun>(`/stores/${storeId}/inventory-advice/runs/${runId}`)).data
}
