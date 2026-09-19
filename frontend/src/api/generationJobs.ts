import type { GenerationJob, GenerationJobEvent, GenerationJobKind, GenerationJobStatus } from "../types/domain"
import { http } from "./http"
import type { PageResponse } from "./types"

export async function createGenerationJob(
  productId: number,
  payload: {
    creative_plan_id: number
    creative_plan_version_no: number
    idempotency_key: string
    size?: string
    duration_seconds?: number
  },
): Promise<GenerationJob> {
  return (await http.post<GenerationJob>(`/products/${productId}/generation-jobs`, payload)).data
}

export async function getGenerationJobs(
  productId: number,
  params: {
    job_kind?: GenerationJobKind
    job_status?: GenerationJobStatus
    page: number
    page_size: number
  },
): Promise<PageResponse<GenerationJob>> {
  return (await http.get<PageResponse<GenerationJob>>(`/products/${productId}/generation-jobs`, { params })).data
}

export async function getGenerationJob(productId: number, jobId: number): Promise<GenerationJob> {
  return (await http.get<GenerationJob>(`/products/${productId}/generation-jobs/${jobId}`)).data
}

export async function getGenerationJobEvents(productId: number, jobId: number): Promise<GenerationJobEvent[]> {
  return (await http.get<GenerationJobEvent[]>(`/products/${productId}/generation-jobs/${jobId}/events`)).data
}

export async function cancelGenerationJob(
  productId: number,
  jobId: number,
  payload: { expected_version: number; reason?: string },
): Promise<GenerationJob> {
  return (await http.post<GenerationJob>(`/products/${productId}/generation-jobs/${jobId}/cancel`, payload)).data
}

export async function retryGenerationJob(
  productId: number,
  jobId: number,
  payload: { expected_version: number; reason?: string },
): Promise<GenerationJob> {
  return (await http.post<GenerationJob>(`/products/${productId}/generation-jobs/${jobId}/retry`, payload)).data
}
