export type UserRole = "admin" | "operator" | "viewer"
export type UserStatus = "active" | "inactive"

export type Permission =
  | "user.manage"
  | "store.manage"
  | "product.write"
  | "inventory.write"
  | "competitor.write"
  | "ai.generate"
  | "job.operate"
  | "asset.review"
  | "ad.confirm"
  | "experiment.write"
  | "performance.write"
  | "settings.manage"

export interface User {
  id: number
  username: string
  display_name: string
  role: UserRole
  status: UserStatus
  last_login_at: string | null
  created_at: string
  updated_at: string
}

export type StorePlatform =
  | "taobao"
  | "tmall"
  | "jd"
  | "pinduoduo"
  | "douyin"
  | "kuaishou"
  | "xiaohongshu"
  | "wechat"
  | "other"
export type EntityStatus = "active" | "inactive"
export type ProductStatus = "draft" | EntityStatus
export type MappingStatus = "active" | "inactive" | "invalid"
export type AuthorizationStatus = "unconfigured" | "pending" | "authorized" | "expired" | "revoked" | "failed"
export type InventoryMovementType = "inbound" | "outbound" | "adjustment" | "lock" | "unlock"

export interface Store {
  id: number
  store_name: string
  platform: StorePlatform
  external_store_id: string | null
  owner_user_id: number | null
  owner_name: string | null
  status: EntityStatus
  remark: string | null
  product_count: number
  low_stock_count: number
  created_at: string
  updated_at: string
}

export interface StoreSummary {
  store_id: number
  product_count: number
  sku_count: number
  low_stock_count: number
  platform_account_count: number
  authorized_account_count: number
}

export interface PlatformAccount {
  id: number
  store_id: number
  platform: StorePlatform
  account_name_masked: string
  auth_status: AuthorizationStatus
  auth_meta: {
    seller_id: string | null
    scopes: string[]
    expires_at: string | null
    last_authorized_at: string | null
    last_error_code: string | null
  }
  remark: string | null
  created_at: string
  updated_at: string
}

export interface Product {
  id: number
  store_id: number
  store_name: string
  name: string
  platform: StorePlatform
  category: string | null
  price: string
  cost: string | null
  target_audience: string | null
  selling_points: string | null
  product_url: string | null
  images: string[]
  status: ProductStatus
  mapping_count: number
  last_diagnosis_at: string | null
  last_review_at: string | null
  created_at: string
  updated_at: string
}

export interface ProductMapping {
  id: number
  store_id: number
  product_id: number
  platform: StorePlatform
  platform_product_id: string
  platform_sku_id: string
  mapping_status: MappingStatus
  created_at: string
  updated_at: string
}

export interface ProductSku {
  id: number
  product_id: number
  product_name: string
  store_id: number
  sku_code: string
  sku_name: string
  specs: Record<string, string>
  price: string
  cost: string | null
  status: EntityStatus
  platform_sku_id: string | null
  created_at: string
  updated_at: string
}

export interface Inventory {
  id: number
  store_id: number
  store_name: string
  product_id: number
  product_name: string
  sku_id: number
  sku_code: string
  sku_name: string
  sku_status: EntityStatus
  stock_qty: number
  locked_qty: number
  available_qty: number
  warning_threshold: number
  is_low_stock: boolean
  location_text: string | null
  version_no: number
  updated_at: string
}

export interface InventoryMovement {
  id: number
  sku_id: number
  movement_type: InventoryMovementType
  quantity_type: "stock" | "locked"
  change_qty: number
  before_qty: number
  after_qty: number
  reason_text: string | null
  reference_type: string | null
  reference_id: string | null
  created_by: number | null
  created_at: string
}

export type AdviceAction = "replenish" | "monitor" | "healthy"
export type AdvicePriority = "critical" | "high" | "medium" | "low"

export interface InventoryAdviceItem {
  id: number
  product_id: number
  product_name: string
  sku_id: number
  sku_code: string
  sku_name: string
  stock_qty: number
  locked_qty: number
  available_qty: number
  warning_threshold: number
  outbound_qty: number
  outbound_events: number
  daily_outbound_rate: string
  target_stock_qty: number
  suggested_restock_qty: number
  action: AdviceAction
  priority: AdvicePriority
  data_status: "sufficient" | "insufficient"
  explanation: string
}

export interface InventoryAdviceRun {
  id: number
  store_id: number
  store_name: string
  rule_version: string
  lookback_days: number
  coverage_days: number
  safety_multiplier: string
  min_outbound_events: number
  item_count: number
  replenish_count: number
  insufficient_count: number
  message: string | null
  generated_by: number | null
  generated_at: string
  items: InventoryAdviceItem[]
}

export type CompetitorFieldSource = "manual" | "parsed" | "monitor"
export type ParseTaskStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled" | "timeout"
export type MonitorStatus = "active" | "paused" | "failed"

export interface Competitor {
  id: number
  product_id: number
  name: string
  platform: StorePlatform
  url: string | null
  price: string | null
  sales_hint: string | null
  title: string | null
  main_image: string | null
  selling_points: string | null
  review_keywords: string | null
  status: EntityStatus
  field_sources: Record<string, CompetitorFieldSource>
  last_parsed_at: string | null
  created_at: string
  updated_at: string
}

export interface ParseResult {
  title: string | null
  price: string | null
  sales_hint: string | null
  main_image: string | null
  selling_points: string | null
  review_keywords: string | null
}

export interface LinkParseTask {
  id: number
  product_id: number
  competitor_id: number | null
  source_url: string
  task_status: ParseTaskStatus
  attempts: number
  max_attempts: number
  result: ParseResult | null
  final_url: string | null
  http_status: number | null
  error_code: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  applied_at: string | null
  applied_by: number | null
  created_at: string
  updated_at: string
}

export interface CompetitorMonitor {
  id: number
  competitor_id: number
  monitor_status: MonitorStatus
  interval_minutes: number
  next_run_at: string | null
  last_error: string | null
  last_error_code: string | null
  consecutive_failures: number
  last_run_at: string | null
  last_success_at: string | null
  created_at: string
  updated_at: string
}

export interface MonitorSnapshot {
  id: number
  monitor_id: number
  price: string | null
  sales_hint: string | null
  title: string | null
  main_image: string | null
  selling_points: string | null
  review_keywords: string | null
  source_url: string | null
  changed_fields: string[]
  is_success: boolean
  error_code: string | null
  error_message: string | null
  created_at: string
}

export interface ProductDiagnosis {
  id: number
  product_id: number
  source_type: string
  source_review_report_id: number | null
  positioning: string
  price_band: string
  audience_insights: string
  pain_points: string
  selling_point_analysis: string
  risks: string
  recommendations: string
  input_snapshot: {
    product?: Record<string, unknown>
    competitors?: Array<Record<string, unknown>>
    sku_inventory?: Array<Record<string, unknown>>
    source_review?: Record<string, unknown> | null
    operator_notes?: string | null
    snapshot_at?: string
  }
  model_name: string
  provider_name: string
  prompt_version: string
  schema_version: string
  generated_by: number | null
  edited_by: number | null
  edited_at: string | null
  version_no: number
  created_at: string
  updated_at: string
}

export type CreativePlanType = "main_image" | "video_script"
export type CreativePlanStatus = "draft" | "selected" | "archived"

export interface MainImagePlanContent {
  title: string
  visual_concept: string
  composition: string
  copy_text: string
  generation_prompt: string
  rationale: string
}

export interface VideoScene {
  order: number
  visual: string
  voiceover: string
  duration_seconds: number
}

export interface VideoScriptContent {
  title: string
  hook: string
  scenes: VideoScene[]
  call_to_action: string
  rationale: string
}

export interface CreativePlan {
  id: number
  product_id: number
  plan_type: CreativePlanType
  generation_batch_id: string | null
  title: string
  content: MainImagePlanContent | VideoScriptContent
  rationale: string | null
  status: CreativePlanStatus
  input_snapshot: Record<string, unknown>
  provider_name: string
  model_name: string
  prompt_version: string
  schema_version: string
  generated_by: number | null
  edited_by: number | null
  edited_at: string | null
  version_no: number
  created_at: string
  updated_at: string
}

export interface CreativePlanRevision {
  id: number
  creative_plan_id: number
  version_no: number
  title: string
  content: MainImagePlanContent | VideoScriptContent
  rationale: string | null
  status: CreativePlanStatus
  changed_by: number | null
  created_at: string
}

export type GenerationJobKind = "image" | "video"
export type GenerationJobStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled" | "timeout"

export interface GenerationJob {
  id: number
  product_id: number
  creative_plan_id: number
  creative_plan_version_no: number
  job_kind: GenerationJobKind
  job_status: GenerationJobStatus
  idempotency_key: string
  provider_name: string | null
  external_job_id: string | null
  input_snapshot: Record<string, unknown>
  attempts: number
  max_attempts: number
  progress_percent: number
  next_run_at: string | null
  result: Record<string, unknown> | null
  error_code: string | null
  error_message: string | null
  requested_by: number | null
  started_at: string | null
  finished_at: string | null
  cancelled_at: string | null
  cancelled_by: number | null
  version_no: number
  created_at: string
  updated_at: string
}

export interface GenerationJobEvent {
  id: number
  job_id: number
  event_type: string
  event_message: string | null
  event_data: Record<string, unknown>
  created_at: string
}

export type AssetType = "image" | "video"
export type AssetReviewStatus = "pending" | "approved" | "rejected"
export type AssetFileStatus = "available" | "missing" | "invalid"

export interface GeneratedAsset {
  id: number
  product_id: number
  creative_plan_id: number
  generation_job_id: number | null
  source_asset_index: number
  asset_type: AssetType
  storage_key: string
  content_url: string
  mime_type: string | null
  file_size_bytes: number
  checksum_sha256: string | null
  file_status: AssetFileStatus
  model_name: string | null
  width: number | null
  height: number | null
  duration_sec: string | null
  review_status: AssetReviewStatus
  reviewed_by: number | null
  reviewed_at: string | null
  version_no: number
  lock_version: number
  usage_scene: string | null
  score: string | null
  tags: string[]
  remark: string | null
  synced_at: string | null
  created_at: string
  updated_at: string
}

export type PromotionLinkStatus = "active" | "inactive"

export interface PromotionLink {
  id: number
  product_id: number
  link_name: string
  target_url: string
  redirect_path: string
  tracking_code: string
  utm: Record<string, string>
  status: PromotionLinkStatus
  click_count: number
  scene_text: string | null
  lock_version: number
  created_at: string
  updated_at: string
}

export interface PromotionLinkSuggestion {
  link_name: string
  target_url: string
  scene_text: string
  utm: Record<string, string>
}

export interface PromotionLinkStatistics {
  promotion_link_id: number
  period_start: string
  period_end: string
  counted_clicks: number
  filtered_clicks: number
  unique_visitors: number
  daily: Array<{
    day: string
    counted_clicks: number
    filtered_clicks: number
    unique_visitors: number
  }>
}

export type AdRecommendationStatus = "pending" | "confirmed" | "rejected"

export interface AdRecommendation {
  id: number
  product_id: number
  summary_text: string
  objective_text: string
  audience_segments: Array<Record<string, unknown>>
  budget_plan: Record<string, unknown>
  creative_tests: Array<Record<string, unknown>>
  bid_strategy: Record<string, unknown>
  risk_controls: string[]
  next_steps: string[]
  confirm_status: AdRecommendationStatus
  confirmed_by: number | null
  confirmed_at: string | null
  confirm_remark: string | null
  input_snapshot: {
    approved_assets?: Array<Record<string, unknown>>
    promotion_links?: Array<Record<string, unknown>>
    latest_diagnosis?: Record<string, unknown> | null
  }
  provider_name: string
  model_name: string
  prompt_version: string
  schema_version: string
  generated_by: number | null
  version_no: number
  created_at: string
  updated_at: string
}

export type AdExperimentStatus = "draft" | "confirmed" | "running" | "finished" | "cancelled"

export interface AdExperiment {
  id: number
  product_id: number
  recommendation_id: number | null
  related_asset_id: number | null
  related_link_id: number | null
  experiment_name: string
  target_text: string | null
  audience_text: string | null
  budget_amount: string
  success_metric_text: string | null
  hypothesis_text: string | null
  experiment_status: AdExperimentStatus
  version_no: number
  created_at: string
  updated_at: string
}

export type PerformanceRecordStatus = "active" | "voided"

export interface PerformanceRecord {
  id: number
  product_id: number
  creative_plan_id: number | null
  generated_asset_id: number | null
  promotion_link_id: number | null
  experiment_id: number | null
  period_start: string
  period_end: string
  impressions: number
  clicks: number
  ctr: string | null
  conversions: number
  conversion_rate: string | null
  spend: string
  revenue: string
  roi: string | null
  notes: string | null
  record_status: PerformanceRecordStatus
  version_no: number
  created_by: number | null
  updated_by: number | null
  voided_by: number | null
  voided_at: string | null
  created_at: string
  updated_at: string
}

export interface PerformanceSummary {
  period_start: string | null
  period_end: string | null
  record_count: number
  impressions: number
  clicks: number
  ctr: string | null
  conversions: number
  conversion_rate: string | null
  spend: string
  revenue: string
  roi: string | null
}

export interface ReviewReport {
  id: number
  product_id: number
  period_start: string
  period_end: string
  summary: string
  core_insights: string[]
  problem_assessment: string[]
  next_actions: string[]
  input_snapshot: {
    aggregate?: Record<string, unknown>
    records?: Array<Record<string, unknown>>
    operator_notes?: string | null
  }
  provider_name: string
  model_name: string
  prompt_version: string
  schema_version: string
  generated_by: number | null
  edited_by: number | null
  edited_at: string | null
  version_no: number
  follow_up_diagnoses: Array<{ id: number; version_no: number; created_at: string }>
  created_at: string
  updated_at: string
}

export interface ReviewReportRevision {
  id: number
  review_report_id: number
  version_no: number
  summary: string
  core_insights: string[]
  problem_assessment: string[]
  next_actions: string[]
  changed_by: number | null
  created_at: string
}

export type ImportType = "products" | "sku_inventory" | "performance_records"
export type ImportBatchStatus = "uploaded" | "validated" | "importing" | "completed" | "failed" | "cancelled"
export type ImportRowStatus = "valid" | "invalid" | "imported" | "failed"

export interface ImportErrorItem {
  column: string | null
  code: string
  message: string
}

export interface ImportRow {
  id: number
  batch_id: number
  row_number: number
  row_status: ImportRowStatus
  raw_data: Record<string, string>
  normalized_data: Record<string, unknown> | null
  errors: ImportErrorItem[]
  target_type: string | null
  target_id: string | null
}

export interface ImportBatch {
  id: number
  import_type: ImportType
  batch_status: ImportBatchStatus
  original_filename: string
  idempotency_key: string
  total_rows: number
  valid_rows: number
  success_rows: number
  failed_rows: number
  created_by: number | null
  confirmed_at: string | null
  created_at: string
  updated_at: string
}

export interface ImportPreview {
  batch: ImportBatch
  rows: ImportRow[]
  field_notes: Record<string, string>
}

export interface DemoDataResult {
  created: boolean
  marker: string
  store_id: number
  product_id: number
  sku_id: number
  object_ids: Record<string, number>
  message: string
}

export interface DashboardData {
  platform: string | null
  available_platforms: string[]
  metrics: { store_count: number; product_count: number; low_stock_count: number; active_job_count: number; pending_asset_count: number; review_report_count: number }
  stores: Array<{ id: number; store_name: string; platform: string; status: string; product_count: number; low_stock_count: number; active_job_count: number; latest_review_at: string | null }>
  products: Array<{ id: number; name: string; store_id: number; store_name: string; platform: string; status: string; low_stock_count: number; latest_job_status: string | null; latest_review_at: string | null }>
  low_stock: Array<{ product_id: number; product_name: string; sku_id: number; sku_code: string; available_qty: number; warning_threshold: number }>
  recent_jobs: Array<{ id: number; product_id: number; product_name: string; job_kind: string; job_status: string; progress_percent: number; created_at: string }>
  recent_reviews: Array<{ id: number; product_id: number; product_name: string; period_start: string; period_end: string; roi: string | null; created_at: string }>
  has_demo_data: boolean
}

export type SettingGroup = "model" | "system" | "queue"
export type SettingApplyMode = "immediate" | "new_requests" | "worker_restart" | "service_restart"
export interface SettingItem { key: string; group: SettingGroup; label: string; description: string; value_type: "string" | "integer" | "boolean" | "decimal" | "json"; value: unknown | null; sensitive: boolean; configured: boolean; source: "environment" | "database"; apply_mode: SettingApplyMode; updated_at: string | null }
export interface SettingsData { groups: Record<SettingGroup, SettingItem[]> }
