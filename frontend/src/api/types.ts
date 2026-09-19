export interface ApiErrorPayload {
  code: string
  message: string
  request_id: string
  details: unknown
}

export interface PageResponse<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

