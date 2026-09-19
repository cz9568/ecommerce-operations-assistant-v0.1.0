import type {
  PerformanceRecord,
  PerformanceRecordStatus,
  PerformanceSummary,
  ReviewReport,
  ReviewReportRevision,
} from "../types/domain"
import { http } from "./http"
import type { PageResponse } from "./types"

export interface PerformancePayload {
  creative_plan_id?: number | null
  generated_asset_id?: number | null
  promotion_link_id?: number | null
  experiment_id?: number | null
  period_start: string
  period_end: string
  impressions: number
  clicks: number
  conversions: number
  spend: number
  revenue: number
  notes?: string | null
}

export async function getPerformanceRecords(productId: number, status?: PerformanceRecordStatus | ""): Promise<PageResponse<PerformanceRecord>> {
  return (await http.get<PageResponse<PerformanceRecord>>(`/products/${productId}/performance-records`, { params: { status: status || undefined, page: 1, page_size: 100 } })).data
}

export async function getPerformanceSummary(productId: number): Promise<PerformanceSummary> {
  return (await http.get<PerformanceSummary>(`/products/${productId}/performance-records/summary`)).data
}

export async function createPerformanceRecord(productId: number, payload: PerformancePayload): Promise<PerformanceRecord> {
  return (await http.post<PerformanceRecord>(`/products/${productId}/performance-records`, payload)).data
}

export async function updatePerformanceRecord(productId: number, recordId: number, payload: PerformancePayload & { expected_version: number }): Promise<PerformanceRecord> {
  return (await http.patch<PerformanceRecord>(`/products/${productId}/performance-records/${recordId}`, payload)).data
}

export async function voidPerformanceRecord(productId: number, recordId: number, expectedVersion: number): Promise<PerformanceRecord> {
  return (await http.delete<PerformanceRecord>(`/products/${productId}/performance-records/${recordId}`, { params: { expected_version: expectedVersion } })).data
}

export async function getReviewReports(productId: number): Promise<PageResponse<ReviewReport>> {
  return (await http.get<PageResponse<ReviewReport>>(`/products/${productId}/review-reports`, { params: { page: 1, page_size: 100 } })).data
}

export async function generateReviewReport(productId: number, payload: { period_start: string; period_end: string; notes?: string }): Promise<ReviewReport> {
  return (await http.post<ReviewReport>(`/products/${productId}/review-reports/generate`, payload, { timeout: 120_000 })).data
}

export async function updateReviewReport(productId: number, reportId: number, payload: Record<string, unknown>): Promise<ReviewReport> {
  return (await http.patch<ReviewReport>(`/products/${productId}/review-reports/${reportId}`, payload)).data
}

export async function getReviewReportRevisions(productId: number, reportId: number): Promise<ReviewReportRevision[]> {
  return (await http.get<ReviewReportRevision[]>(`/products/${productId}/review-reports/${reportId}/revisions`)).data
}
