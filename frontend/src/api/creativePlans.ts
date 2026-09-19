import type {
  CreativePlan,
  CreativePlanRevision,
  CreativePlanStatus,
  CreativePlanType,
  MainImagePlanContent,
  VideoScriptContent,
} from "../types/domain"
import { http } from "./http"
import type { PageResponse } from "./types"

export async function getCreativePlans(
  productId: number,
  params: {
    plan_type: CreativePlanType
    plan_status?: CreativePlanStatus
    page: number
    page_size: number
  },
): Promise<PageResponse<CreativePlan>> {
  return (await http.get<PageResponse<CreativePlan>>(`/products/${productId}/creative-plans`, { params })).data
}

export async function generateCreativePlans(
  productId: number,
  payload: { plan_type: CreativePlanType; diagnosis_id?: number; notes?: string },
): Promise<CreativePlan[]> {
  return (await http.post<CreativePlan[]>(`/products/${productId}/creative-plans/generate`, payload)).data
}

export async function updateCreativePlan(
  productId: number,
  planId: number,
  payload: {
    content: MainImagePlanContent | VideoScriptContent
    expected_version: number
  },
): Promise<CreativePlan> {
  return (await http.patch<CreativePlan>(`/products/${productId}/creative-plans/${planId}`, payload)).data
}

export async function updateCreativePlanStatus(
  productId: number,
  planId: number,
  payload: { status: CreativePlanStatus; expected_version: number },
): Promise<CreativePlan> {
  return (await http.post<CreativePlan>(`/products/${productId}/creative-plans/${planId}/status`, payload)).data
}

export async function getCreativePlanRevisions(
  productId: number,
  planId: number,
): Promise<CreativePlanRevision[]> {
  return (await http.get<CreativePlanRevision[]>(`/products/${productId}/creative-plans/${planId}/revisions`)).data
}
