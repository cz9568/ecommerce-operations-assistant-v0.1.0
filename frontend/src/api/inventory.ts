import type { EntityStatus, Inventory, InventoryMovement, InventoryMovementType, ProductSku } from "../types/domain"
import { http } from "./http"
import type { PageResponse } from "./types"

export interface SkuPayload {
  sku_code: string
  sku_name: string
  specs: Record<string, string>
  price: number
  cost?: number | null
  status: EntityStatus
  platform_sku_id?: string | null
}
export async function getSkus(productId: number, params: { page: number; page_size: number; q?: string; status?: EntityStatus }): Promise<PageResponse<ProductSku>> {
  return (await http.get<PageResponse<ProductSku>>(`/products/${productId}/skus`, { params })).data
}
export async function createSku(productId: number, payload: SkuPayload): Promise<ProductSku> {
  return (await http.post<ProductSku>(`/products/${productId}/skus`, payload)).data
}
export async function updateSku(productId: number, skuId: number, payload: Omit<Partial<SkuPayload>, "status">): Promise<ProductSku> {
  return (await http.patch<ProductSku>(`/products/${productId}/skus/${skuId}`, payload)).data
}
export async function updateSkuStatus(productId: number, skuId: number, status: EntityStatus): Promise<ProductSku> {
  return (await http.patch<ProductSku>(`/products/${productId}/skus/${skuId}/status`, { status })).data
}

export async function getInventory(params: { page: number; page_size: number; store_id?: number; product_id?: number; q?: string; status?: EntityStatus }, lowStock = false): Promise<PageResponse<Inventory>> {
  const path = lowStock ? "/inventory/low-stock" : "/inventory"
  return (await http.get<PageResponse<Inventory>>(path, { params })).data
}
export async function getSkuInventory(productId: number, skuId: number): Promise<Inventory> {
  return (await http.get<Inventory>(`/products/${productId}/skus/${skuId}/inventory`)).data
}
export async function updateInventoryConfig(productId: number, skuId: number, payload: { warning_threshold?: number; location_text?: string | null; expected_version: number }): Promise<Inventory> {
  return (await http.patch<Inventory>(`/products/${productId}/skus/${skuId}/inventory`, payload)).data
}
export async function adjustInventory(productId: number, skuId: number, payload: { movement_type: InventoryMovementType; change_qty: number; reason_text: string; reference_type?: string; reference_id?: string; expected_version: number }): Promise<{ inventory: Inventory; movement: InventoryMovement }> {
  return (await http.post<{ inventory: Inventory; movement: InventoryMovement }>(`/products/${productId}/skus/${skuId}/inventory/adjustments`, payload)).data
}
export async function getInventoryMovements(productId: number, skuId: number, params: { page: number; page_size: number; movement_type?: InventoryMovementType }): Promise<PageResponse<InventoryMovement>> {
  return (await http.get<PageResponse<InventoryMovement>>(`/products/${productId}/skus/${skuId}/inventory/movements`, { params })).data
}
