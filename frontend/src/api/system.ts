import { http } from "./http"

export interface HealthResponse {
  status: "ok" | "unavailable"
  service: string
  database: "not_checked" | "ok" | "unavailable"
}

export async function checkLiveness(): Promise<HealthResponse> {
  const response = await http.get<HealthResponse>("/health/live", { timeout: 3000 })
  return response.data
}

