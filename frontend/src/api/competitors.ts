import type {
  Competitor,
  CompetitorMonitor,
  EntityStatus,
  LinkParseTask,
  MonitorSnapshot,
  MonitorStatus,
  ParseTaskStatus,
  StorePlatform,
} from "../types/domain"
import { http } from "./http"
import type { PageResponse } from "./types"

export type CompetitorField = "name" | "url" | "price" | "sales_hint" | "title" | "main_image" | "selling_points" | "review_keywords"
export interface CompetitorPayload {
  name: string
  platform: StorePlatform
  url?: string | null
  price?: number | null
  sales_hint?: string | null
  title?: string | null
  main_image?: string | null
  selling_points?: string | null
  review_keywords?: string | null
  status: EntityStatus
}

export async function getCompetitors(productId: number, params: { page: number; page_size: number; q?: string; status?: EntityStatus; platform?: StorePlatform }): Promise<PageResponse<Competitor>> {
  return (await http.get<PageResponse<Competitor>>(`/products/${productId}/competitors`, { params })).data
}
export async function createCompetitor(productId: number, payload: CompetitorPayload): Promise<Competitor> {
  return (await http.post<Competitor>(`/products/${productId}/competitors`, payload)).data
}
export async function updateCompetitor(productId: number, competitorId: number, payload: Partial<CompetitorPayload>): Promise<Competitor> {
  return (await http.patch<Competitor>(`/products/${productId}/competitors/${competitorId}`, payload)).data
}
export async function archiveCompetitor(productId: number, competitorId: number): Promise<Competitor> {
  return (await http.delete<Competitor>(`/products/${productId}/competitors/${competitorId}`)).data
}

export async function getParseTasks(productId: number, params: { page: number; page_size: number; status?: ParseTaskStatus }): Promise<PageResponse<LinkParseTask>> {
  return (await http.get<PageResponse<LinkParseTask>>(`/products/${productId}/link-parse-tasks`, { params })).data
}
export async function createParseTask(productId: number, payload: { source_url: string; competitor_id?: number }): Promise<LinkParseTask> {
  return (await http.post<LinkParseTask>(`/products/${productId}/competitors/import-url-tasks`, payload)).data
}
export async function runParseTask(productId: number, taskId: number): Promise<LinkParseTask> {
  return (await http.post<LinkParseTask>(`/products/${productId}/link-parse-tasks/${taskId}/run`)).data
}
export async function applyParseTask(productId: number, taskId: number, payload: { competitor_id?: number; fields: CompetitorField[]; name?: string; platform?: StorePlatform }): Promise<Competitor> {
  return (await http.post<Competitor>(`/products/${productId}/link-parse-tasks/${taskId}/apply`, payload)).data
}

export async function getCompetitorMonitor(productId: number, competitorId: number): Promise<CompetitorMonitor> {
  return (await http.get<CompetitorMonitor>(`/products/${productId}/competitors/${competitorId}/monitor`)).data
}
export async function saveCompetitorMonitor(productId: number, competitorId: number, payload: { monitor_status: "active" | "paused"; interval_minutes: number }): Promise<CompetitorMonitor> {
  return (await http.post<CompetitorMonitor>(`/products/${productId}/competitors/${competitorId}/monitor`, payload)).data
}
export async function runCompetitorMonitor(productId: number, competitorId: number): Promise<CompetitorMonitor> {
  return (await http.post<CompetitorMonitor>(`/products/${productId}/competitors/${competitorId}/monitor/run`)).data
}
export async function getMonitorSnapshots(productId: number, competitorId: number, params: { page: number; page_size: number }): Promise<PageResponse<MonitorSnapshot>> {
  return (await http.get<PageResponse<MonitorSnapshot>>(`/products/${productId}/competitors/${competitorId}/monitor/snapshots`, { params })).data
}
export async function applyMonitorSnapshot(productId: number, competitorId: number, snapshotId: number, fields: CompetitorField[]): Promise<Competitor> {
  return (await http.post<Competitor>(`/products/${productId}/competitors/${competitorId}/monitor/snapshots/${snapshotId}/apply`, { fields })).data
}

export type { MonitorStatus }
