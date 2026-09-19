import type {
  AssetFileStatus,
  AssetReviewStatus,
  AssetType,
  GeneratedAsset,
} from "../types/domain"
import { http } from "./http"
import type { PageResponse } from "./types"

export async function getAssets(
  productId: number,
  params: {
    asset_type?: AssetType
    review_status?: AssetReviewStatus
    file_status?: AssetFileStatus
    page: number
    page_size: number
  },
): Promise<PageResponse<GeneratedAsset>> {
  return (await http.get<PageResponse<GeneratedAsset>>(`/products/${productId}/assets`, { params })).data
}

export async function getAsset(productId: number, assetId: number): Promise<GeneratedAsset> {
  return (await http.get<GeneratedAsset>(`/products/${productId}/assets/${assetId}`)).data
}

export async function getAssetContentBlob(productId: number, assetId: number): Promise<Blob> {
  return (
    await http.get<Blob>(`/products/${productId}/assets/${assetId}/content`, {
      responseType: "blob",
      timeout: 120_000,
    })
  ).data
}

export async function updateAsset(
  productId: number,
  assetId: number,
  payload: {
    expected_lock_version: number
    usage_scene?: string | null
    score?: number | null
    tags?: string[]
    remark?: string | null
  },
): Promise<GeneratedAsset> {
  return (await http.patch<GeneratedAsset>(`/products/${productId}/assets/${assetId}`, payload)).data
}

export async function reviewAsset(
  productId: number,
  assetId: number,
  payload: {
    expected_lock_version: number
    review_status: AssetReviewStatus
    remark?: string
  },
): Promise<GeneratedAsset> {
  return (await http.post<GeneratedAsset>(`/products/${productId}/assets/${assetId}/review`, payload)).data
}

export async function checkAssetFile(productId: number, assetId: number): Promise<GeneratedAsset> {
  return (await http.post<GeneratedAsset>(`/products/${productId}/assets/${assetId}/check`)).data
}

export async function syncJobAssets(productId: number, jobId: number): Promise<GeneratedAsset[]> {
  return (await http.post<GeneratedAsset[]>(`/products/${productId}/assets/sync/${jobId}`)).data
}
