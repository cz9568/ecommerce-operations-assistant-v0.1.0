import type { User, UserRole, UserStatus } from "../types/domain"
import { http } from "./http"
import type { PageResponse } from "./types"

export interface UserQuery {
  page: number
  page_size: number
  q?: string
  role?: UserRole
  status?: UserStatus
}

export interface CreateUserPayload {
  username: string
  display_name: string
  password: string
  role: UserRole
  status: UserStatus
}

export interface UpdateUserPayload {
  display_name?: string
  password?: string
  role?: UserRole
  status?: UserStatus
}

export async function getUsers(params: UserQuery): Promise<PageResponse<User>> {
  const response = await http.get<PageResponse<User>>("/users", { params })
  return response.data
}

export async function createUser(payload: CreateUserPayload): Promise<User> {
  const response = await http.post<User>("/users", payload)
  return response.data
}

export async function updateUser(userId: number, payload: UpdateUserPayload): Promise<User> {
  const response = await http.patch<User>(`/users/${userId}`, payload)
  return response.data
}

