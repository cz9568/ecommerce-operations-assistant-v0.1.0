import type { MappingStatus, Product, ProductMapping, ProductStatus, StorePlatform } from "../types/domain"
import { http } from "./http"
import type { PageResponse } from "./types"

export interface ProductQuery {
  page: number
  page_size: number
  q?: string
  store_id?: number
  platform?: StorePlatform
  status?: ProductStatus
  category?: string
}
export interface ProductPayload {
  store_id: number
  name: string
  category?: string | null
  price: number
  cost?: number | null
  target_audience?: string | null
  selling_points?: string | null
  product_url?: string | null
  images: string[]
  status: ProductStatus
}
export interface MappingPayload {
  platform_product_id: string
  platform_sku_id: string
  mapping_status: MappingStatus
}

export async function getProducts(params: ProductQuery): Promise<PageResponse<Product>> {
  return (await http.get<PageResponse<Product>>("/products", { params })).data
}
export async function getProduct(id: number): Promise<Product> {
  return (await http.get<Product>(`/products/${id}`)).data
}
export async function createProduct(payload: ProductPayload): Promise<Product> {
  return (await http.post<Product>("/products", payload)).data
}
export async function updateProduct(id: number, payload: Omit<Partial<ProductPayload>, "store_id" | "status">): Promise<Product> {
  return (await http.patch<Product>(`/products/${id}`, payload)).data
}
export async function updateProductStatus(id: number, status: "active" | "inactive"): Promise<Product> {
  return (await http.patch<Product>(`/products/${id}/status`, { status })).data
}
export async function archiveProduct(id: number): Promise<void> {
  await http.delete(`/products/${id}`)
}
export async function getProductMappings(productId: number): Promise<ProductMapping[]> {
  return (await http.get<ProductMapping[]>(`/products/${productId}/mappings`)).data
}
export async function createProductMapping(productId: number, payload: MappingPayload): Promise<ProductMapping> {
  return (await http.post<ProductMapping>(`/products/${productId}/mappings`, payload)).data
}
export async function updateProductMapping(productId: number, mappingId: number, payload: Partial<MappingPayload>): Promise<ProductMapping> {
  return (await http.patch<ProductMapping>(`/products/${productId}/mappings/${mappingId}`, payload)).data
}
export async function deleteProductMapping(productId: number, mappingId: number): Promise<void> {
  await http.delete(`/products/${productId}/mappings/${mappingId}`)
}
