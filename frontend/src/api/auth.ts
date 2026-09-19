import type { User } from "../types/domain"
import { http } from "./http"

export interface LoginPayload {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: "bearer"
  expires_in: number
}

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  const response = await http.post<TokenResponse>("/auth/login", payload)
  return response.data
}

export async function getCurrentUser(): Promise<User> {
  const response = await http.get<User>("/auth/me")
  return response.data
}

export async function logout(): Promise<void> {
  await http.post("/auth/logout")
}

