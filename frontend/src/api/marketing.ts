import type {
  AdExperiment,
  AdExperimentStatus,
  AdRecommendation,
  PromotionLink,
  PromotionLinkStatistics,
  PromotionLinkSuggestion,
} from "../types/domain"
import { http } from "./http"
import type { PageResponse } from "./types"

export async function suggestPromotionLinks(productId: number, targetUrl?: string): Promise<PromotionLinkSuggestion[]> {
  return (await http.post<{ suggestions: PromotionLinkSuggestion[] }>(`/products/${productId}/promotion-links/generate`, { target_url: targetUrl || null })).data.suggestions
}

export async function getPromotionLinks(productId: number, status?: string): Promise<PageResponse<PromotionLink>> {
  return (await http.get<PageResponse<PromotionLink>>(`/products/${productId}/promotion-links`, { params: { status: status || undefined, page: 1, page_size: 100 } })).data
}

export async function createPromotionLink(productId: number, payload: { link_name: string; target_url: string; scene_text?: string | null; utm: Record<string, string> }): Promise<PromotionLink> {
  return (await http.post<PromotionLink>(`/products/${productId}/promotion-links`, payload)).data
}

export async function updatePromotionLink(productId: number, linkId: number, payload: Record<string, unknown>): Promise<PromotionLink> {
  return (await http.patch<PromotionLink>(`/products/${productId}/promotion-links/${linkId}`, payload)).data
}

export async function getPromotionLinkStatistics(productId: number, linkId: number): Promise<PromotionLinkStatistics> {
  return (await http.get<PromotionLinkStatistics>(`/products/${productId}/promotion-links/${linkId}/statistics`)).data
}

export async function getAdRecommendations(productId: number): Promise<PageResponse<AdRecommendation>> {
  return (await http.get<PageResponse<AdRecommendation>>(`/products/${productId}/ad-recommendations`, { params: { page: 1, page_size: 100 } })).data
}

export async function generateAdRecommendation(productId: number, payload: { asset_ids: number[]; link_ids: number[]; notes?: string }): Promise<AdRecommendation> {
  return (await http.post<AdRecommendation>(`/products/${productId}/ad-recommendations/generate`, payload, { timeout: 120_000 })).data
}

export async function confirmAdRecommendation(productId: number, recommendationId: number, payload: { expected_version: number; confirm_status: "confirmed" | "rejected"; remark?: string }): Promise<AdRecommendation> {
  return (await http.patch<AdRecommendation>(`/products/${productId}/ad-recommendations/${recommendationId}/confirmation`, payload)).data
}

export async function updateAdRecommendation(productId: number, recommendationId: number, payload: Record<string, unknown>): Promise<AdRecommendation> {
  return (await http.patch<AdRecommendation>(`/products/${productId}/ad-recommendations/${recommendationId}`, payload)).data
}

export async function getAdExperiments(productId: number, status?: AdExperimentStatus | ""): Promise<PageResponse<AdExperiment>> {
  return (await http.get<PageResponse<AdExperiment>>(`/products/${productId}/ad-experiments`, { params: { status: status || undefined, page: 1, page_size: 100 } })).data
}

export async function generateAdExperiment(productId: number, payload: { recommendation_id: number; related_asset_id: number; related_link_id: number; experiment_name?: string; budget_amount: number }): Promise<AdExperiment> {
  return (await http.post<AdExperiment>(`/products/${productId}/ad-experiments/generate`, payload)).data
}

export async function updateAdExperiment(productId: number, experimentId: number, payload: Record<string, unknown>): Promise<AdExperiment> {
  return (await http.patch<AdExperiment>(`/products/${productId}/ad-experiments/${experimentId}`, payload)).data
}
