import type {
  AdviceAction,
  AdvicePriority,
  AuthorizationStatus,
  EntityStatus,
  InventoryMovementType,
  MappingStatus,
  ProductStatus,
  StorePlatform,
} from "../types/domain"

export const platformOptions: Array<{ value: StorePlatform; label: string }> = [
  { value: "taobao", label: "淘宝" },
  { value: "tmall", label: "天猫" },
  { value: "jd", label: "京东" },
  { value: "pinduoduo", label: "拼多多" },
  { value: "douyin", label: "抖音" },
  { value: "kuaishou", label: "快手" },
  { value: "xiaohongshu", label: "小红书" },
  { value: "wechat", label: "微信" },
  { value: "other", label: "其他" },
]

export const platformLabels = Object.fromEntries(platformOptions.map((item) => [item.value, item.label])) as Record<StorePlatform, string>
export const entityStatusLabels: Record<EntityStatus, string> = { active: "启用", inactive: "停用" }
export const productStatusLabels: Record<ProductStatus, string> = { draft: "草稿", active: "上架", inactive: "下架" }
export const mappingStatusLabels: Record<MappingStatus, string> = { active: "有效", inactive: "停用", invalid: "失效" }
export const authStatusLabels: Record<AuthorizationStatus, string> = {
  unconfigured: "未配置",
  pending: "授权中",
  authorized: "已授权",
  expired: "已过期",
  revoked: "已撤销",
  failed: "授权失败",
}
export const movementTypeLabels: Record<InventoryMovementType, string> = {
  inbound: "入库",
  outbound: "出库",
  adjustment: "盘点调整",
  lock: "锁定",
  unlock: "解锁",
}
export const adviceActionLabels: Record<AdviceAction, string> = { replenish: "建议补货", monitor: "持续观察", healthy: "库存健康" }
export const advicePriorityLabels: Record<AdvicePriority, string> = { critical: "紧急", high: "高", medium: "中", low: "低" }

export function formatDate(value: string | null | undefined, fallback = "—"): string {
  if (!value) return fallback
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
}

export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—"
  return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(Number(value))
}

export function formatSpecs(specs: Record<string, string>): string {
  const values = Object.entries(specs).map(([key, value]) => `${key}: ${value}`)
  return values.length ? values.join(" / ") : "无规格"
}
