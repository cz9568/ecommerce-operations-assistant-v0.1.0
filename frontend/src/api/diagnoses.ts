import type { ProductDiagnosis } from "../types/domain"
import { http } from "./http"
import type { PageResponse } from "./types"

export type DiagnosisContentField =
  | "positioning"
  | "price_band"
  | "audience_insights"
  | "pain_points"
  | "selling_point_analysis"
  | "risks"
  | "recommendations"

export type DiagnosisUpdatePayload = Record<DiagnosisContentField, string> & {
  expected_version: number
}

export async function getDiagnoses(
  productId: number,
  params: { page: number; page_size: number },
): Promise<PageResponse<ProductDiagnosis>> {
  return (await http.get<PageResponse<ProductDiagnosis>>(`/products/${productId}/diagnoses`, { params })).data
}

export async function generateDiagnosis(
  productId: number,
  payload: { notes?: string; source_review_report_id?: number },
): Promise<ProductDiagnosis> {
  return (await http.post<ProductDiagnosis>(`/products/${productId}/diagnoses/generate`, payload)).data
}

export async function updateDiagnosis(
  productId: number,
  diagnosisId: number,
  payload: DiagnosisUpdatePayload,
): Promise<ProductDiagnosis> {
  return (await http.patch<ProductDiagnosis>(`/products/${productId}/diagnoses/${diagnosisId}`, payload)).data
}
