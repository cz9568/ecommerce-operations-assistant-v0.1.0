import { http } from "./http"
import type { DashboardData } from "../types/domain"

export async function getDashboard(platform?: string): Promise<DashboardData> {
  const { data } = await http.get<DashboardData>("/dashboard", { params: { platform: platform || undefined } })
  return data
}
