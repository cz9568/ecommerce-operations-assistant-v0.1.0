import { http } from "./http"
import type { SettingGroup, SettingsData } from "../types/domain"

export async function getSettings(): Promise<SettingsData> {
  const { data } = await http.get<SettingsData>("/settings")
  return data
}

export async function saveSettings(group: SettingGroup, values: Record<string, unknown>): Promise<SettingsData> {
  const { data } = await http.patch<SettingsData>(`/settings/${group}`, { values })
  return data
}
