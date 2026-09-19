import { http } from "./http"
import type { PageResponse } from "./types"
import type { DemoDataResult, ImportBatch, ImportPreview, ImportType } from "../types/domain"

export async function getImportBatches(importType?: ImportType): Promise<PageResponse<ImportBatch>> {
  const { data } = await http.get<PageResponse<ImportBatch>>("/imports", { params: { import_type: importType, page: 1, page_size: 50 } })
  return data
}

export async function getImportBatch(batchId: number): Promise<ImportPreview> {
  const { data } = await http.get<ImportPreview>(`/imports/${batchId}`)
  return data
}

export async function uploadImport(importType: ImportType, file: File): Promise<ImportPreview> {
  const idempotencyKey = `${importType}-${file.name}-${file.size}-${file.lastModified}`
  const { data } = await http.post<ImportPreview>(`/imports/${importType}/upload`, file, {
    params: { filename: file.name },
    headers: { "Content-Type": "text/csv", "X-Idempotency-Key": idempotencyKey },
    timeout: 30_000,
  })
  return data
}

export async function confirmImport(batchId: number): Promise<ImportPreview> {
  const { data } = await http.post<ImportPreview>(`/imports/${batchId}/confirm`)
  return data
}

function saveBlob(data: Blob, filename: string): void {
  const url = URL.createObjectURL(data)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function downloadImportTemplate(importType: ImportType): Promise<void> {
  const { data } = await http.get<Blob>(`/imports/templates/${importType}`, { responseType: "blob" })
  saveBlob(data, `${importType}-template.csv`)
}

export async function downloadImportErrors(batchId: number): Promise<void> {
  const { data } = await http.get<Blob>(`/imports/${batchId}/errors.csv`, { responseType: "blob" })
  saveBlob(data, `import-${batchId}-errors.csv`)
}

export async function initializeDemoData(rebuild = false): Promise<DemoDataResult> {
  const { data } = await http.post<DemoDataResult>("/demo-data/initialize", undefined, { params: { rebuild } })
  return data
}
