<script setup lang="ts">
import {
  CircleCheck,
  CircleClose,
  EditPen,
  Picture,
  Refresh,
  VideoPlay,
  Warning,
} from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"

import {
  checkAssetFile,
  getAsset,
  getAssetContentBlob,
  getAssets,
  reviewAsset,
  updateAsset,
} from "../../api/assets"
import { getApiErrorMessage } from "../../api/http"
import { useAuthStore } from "../../stores/auth"
import type {
  AssetFileStatus,
  AssetReviewStatus,
  AssetType,
  GeneratedAsset,
} from "../../types/domain"
import { formatDate } from "../../utils/domain"

const props = defineProps<{ productId: number }>()
const authStore = useAuthStore()
const records = ref<GeneratedAsset[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const typeFilter = ref<AssetType | "">("")
const reviewFilter = ref<AssetReviewStatus | "">("")
const fileFilter = ref<AssetFileStatus | "">("")
const loading = ref(false)
const loadError = ref("")
const detailDrawer = ref(false)
const detailLoading = ref(false)
const selected = ref<GeneratedAsset | null>(null)
const previewUrl = ref("")
const previewError = ref("")
const editMode = ref(false)
const saving = ref(false)
const actionLoading = ref(false)
const usageScene = ref("")
const score = ref<number | undefined>(undefined)
const tagsText = ref("")
const remark = ref("")

const canReview = computed(() => authStore.can("asset.review"))
const typeLabels: Record<AssetType, string> = { image: "图片", video: "视频" }
const reviewLabels: Record<AssetReviewStatus, string> = {
  pending: "待审核",
  approved: "已通过",
  rejected: "已驳回",
}
const fileLabels: Record<AssetFileStatus, string> = {
  available: "可用",
  missing: "文件缺失",
  invalid: "文件损坏",
}

function reviewType(status: AssetReviewStatus): "success" | "danger" | "warning" {
  if (status === "approved") return "success"
  if (status === "rejected") return "danger"
  return "warning"
}
function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
function replaceRecord(asset: GeneratedAsset): void {
  records.value = records.value.map((item) => item.id === asset.id ? asset : item)
  if (selected.value?.id === asset.id) selected.value = asset
}
function resetEditor(asset: GeneratedAsset): void {
  usageScene.value = asset.usage_scene || ""
  score.value = asset.score === null ? undefined : Number(asset.score)
  tagsText.value = asset.tags.join("，")
  remark.value = asset.remark || ""
}
function releasePreview(): void {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ""
}

async function loadRecords(): Promise<void> {
  loading.value = true
  try {
    const result = await getAssets(props.productId, {
      asset_type: typeFilter.value || undefined,
      review_status: reviewFilter.value || undefined,
      file_status: fileFilter.value || undefined,
      page: page.value,
      page_size: pageSize,
    })
    records.value = result.items
    total.value = result.total
    loadError.value = ""
  } catch (error) {
    loadError.value = getApiErrorMessage(error, "素材库加载失败")
  } finally {
    loading.value = false
  }
}
async function filterChanged(): Promise<void> {
  page.value = 1
  await loadRecords()
}
async function changePage(value: number): Promise<void> {
  page.value = value
  await loadRecords()
}
async function openAsset(asset: GeneratedAsset): Promise<void> {
  releasePreview()
  selected.value = asset
  resetEditor(asset)
  previewError.value = ""
  editMode.value = false
  detailDrawer.value = true
  detailLoading.value = true
  try {
    const latest = await getAsset(props.productId, asset.id)
    selected.value = latest
    replaceRecord(latest)
    resetEditor(latest)
    if (latest.file_status === "available") {
      const blob = await getAssetContentBlob(props.productId, latest.id)
      previewUrl.value = URL.createObjectURL(blob)
    } else {
      previewError.value = "素材文件当前不可用，请由有权限的用户检查或重新同步来源任务。"
    }
  } catch (error) {
    previewError.value = getApiErrorMessage(error, "素材预览加载失败")
  } finally {
    detailLoading.value = false
  }
}
function closeDetail(): void {
  releasePreview()
  selected.value = null
  editMode.value = false
}
async function saveMetadata(): Promise<void> {
  if (!selected.value) return
  const tags = tagsText.value.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean)
  if (tags.length > 20) {
    ElMessage.warning("标签最多 20 个")
    return
  }
  saving.value = true
  try {
    const updated = await updateAsset(props.productId, selected.value.id, {
      expected_lock_version: selected.value.lock_version,
      usage_scene: usageScene.value.trim() || null,
      score: score.value ?? null,
      tags,
      remark: remark.value.trim() || null,
    })
    replaceRecord(updated)
    resetEditor(updated)
    editMode.value = false
    ElMessage.success("素材信息已保存")
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "保存失败，请刷新后重试"))
    if (selected.value) await openAsset(selected.value)
  } finally {
    saving.value = false
  }
}
async function changeReviewStatus(status: AssetReviewStatus): Promise<void> {
  if (!selected.value) return
  const action = status === "approved" ? "审核通过" : status === "rejected" ? "驳回" : "撤回审核"
  try {
    const result = await ElMessageBox.prompt(
      status === "approved" ? "确认该素材文件完整且符合使用要求。审核备注可选。" : `请输入${action}原因（选填）。`,
      action,
      { type: status === "rejected" ? "warning" : "info", confirmButtonText: `确认${action}`, inputPlaceholder: "审核备注（选填）" },
    )
    actionLoading.value = true
    const updated = await reviewAsset(props.productId, selected.value.id, {
      expected_lock_version: selected.value.lock_version,
      review_status: status,
      remark: result.value?.trim() || undefined,
    })
    replaceRecord(updated)
    resetEditor(updated)
    ElMessage.success(`素材已${action}`)
  } catch (error) {
    if (error === "cancel" || error === "close") return
    ElMessage.error(getApiErrorMessage(error, `${action}失败`))
    if (selected.value) await openAsset(selected.value)
  } finally {
    actionLoading.value = false
  }
}
async function verifyFile(): Promise<void> {
  if (!selected.value) return
  actionLoading.value = true
  try {
    const updated = await checkAssetFile(props.productId, selected.value.id)
    replaceRecord(updated)
    ElMessage.success(updated.file_status === "available" ? "素材文件校验通过" : "已更新文件失效状态")
    await openAsset(updated)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "文件检查失败"))
  } finally {
    actionLoading.value = false
  }
}

onMounted(() => void loadRecords())
onBeforeUnmount(releasePreview)
watch(() => props.productId, () => {
  closeDetail()
  page.value = 1
  void loadRecords()
})
</script>

<template>
  <section class="asset-panel">
    <header class="panel-head">
      <div><p>GENERATED ASSET LIBRARY</p><h2>商品素材库</h2><span>生成结果已转存到受控存储，可按版本追溯、预览、评分和审核。</span></div>
      <div class="filters">
        <el-select v-model="typeFilter" clearable placeholder="全部媒体" @change="filterChanged"><el-option label="图片" value="image" /><el-option label="视频" value="video" /></el-select>
        <el-select v-model="reviewFilter" clearable placeholder="全部审核状态" @change="filterChanged"><el-option v-for="(label, status) in reviewLabels" :key="status" :label="label" :value="status" /></el-select>
        <el-select v-model="fileFilter" clearable placeholder="全部文件状态" @change="filterChanged"><el-option v-for="(label, status) in fileLabels" :key="status" :label="label" :value="status" /></el-select>
        <el-button :icon="Refresh" :loading="loading" @click="loadRecords">刷新</el-button>
      </div>
    </header>
    <el-alert v-if="loadError" :title="loadError" type="error" show-icon :closable="false"><template #default><el-button link type="primary" @click="loadRecords">重新加载</el-button></template></el-alert>

    <div v-loading="loading" class="asset-grid">
      <article v-for="asset in records" :key="asset.id" class="asset-card" @click="openAsset(asset)">
        <div class="media-placeholder" :class="[`type-${asset.asset_type}`, `file-${asset.file_status}`]">
          <el-icon :size="42"><Picture v-if="asset.asset_type === 'image'" /><VideoPlay v-else /></el-icon>
          <span v-if="asset.file_status !== 'available'"><el-icon><Warning /></el-icon>{{ fileLabels[asset.file_status] }}</span>
          <small>{{ typeLabels[asset.asset_type] }} · 点击安全预览</small>
        </div>
        <div class="asset-body">
          <div class="asset-title"><div><small>#{{ asset.id }} · 素材 v{{ asset.version_no }}</small><h3>{{ asset.usage_scene || `${typeLabels[asset.asset_type]}候选素材` }}</h3></div><el-tag :type="reviewType(asset.review_status)" effect="plain">{{ reviewLabels[asset.review_status] }}</el-tag></div>
          <div class="meta"><span>方案 #{{ asset.creative_plan_id }}</span><span>{{ formatBytes(asset.file_size_bytes) }}</span><span>{{ formatDate(asset.created_at) }}</span></div>
          <div class="tags"><el-tag v-for="tag in asset.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag><span v-if="!asset.tags.length">暂无标签</span></div>
          <div class="score"><span>评分</span><el-rate :model-value="asset.score === null ? 0 : Number(asset.score)" disabled /></div>
        </div>
      </article>
      <el-empty v-if="!records.length && !loading" description="尚无生成素材，请先运行图片或视频生成任务" />
    </div>
    <el-pagination v-if="total > pageSize" class="pager" background layout="prev,pager,next,total" :current-page="page" :page-size="pageSize" :total="total" @update:current-page="changePage" />

    <el-drawer v-model="detailDrawer" size="min(860px, 96vw)" @closed="closeDetail">
      <template #header><div v-if="selected" class="drawer-title"><div><small>ASSET #{{ selected.id }}</small><h3>{{ selected.usage_scene || `${typeLabels[selected.asset_type]}素材 v${selected.version_no}` }}</h3></div><div><el-tag :type="reviewType(selected.review_status)" effect="plain">{{ reviewLabels[selected.review_status] }}</el-tag><el-tag v-if="selected.file_status !== 'available'" type="danger" effect="plain">{{ fileLabels[selected.file_status] }}</el-tag></div></div></template>
      <div v-if="selected" v-loading="detailLoading" class="asset-detail">
        <div class="preview-stage">
          <el-image v-if="selected.asset_type === 'image' && previewUrl" :src="previewUrl" fit="contain" :preview-src-list="[previewUrl]" preview-teleported />
          <video v-else-if="selected.asset_type === 'video' && previewUrl" :src="previewUrl" controls preload="metadata" />
          <el-empty v-else :description="previewError || '正在加载安全预览'" :image-size="80" />
        </div>
        <el-alert v-if="previewError" :title="previewError" type="error" show-icon :closable="false" />
        <div class="toolbar">
          <el-button v-if="canReview" :icon="EditPen" @click="editMode = !editMode">{{ editMode ? '取消编辑' : '编辑信息' }}</el-button>
          <el-button v-if="canReview" :icon="Refresh" :loading="actionLoading" @click="verifyFile">检查文件</el-button>
          <el-button v-if="canReview && selected.review_status !== 'approved'" type="success" plain :icon="CircleCheck" :loading="actionLoading" :disabled="selected.file_status !== 'available'" @click="changeReviewStatus('approved')">审核通过</el-button>
          <el-button v-if="canReview && selected.review_status !== 'rejected'" type="danger" plain :icon="CircleClose" :loading="actionLoading" @click="changeReviewStatus('rejected')">驳回</el-button>
          <el-button v-if="canReview && selected.review_status !== 'pending'" :loading="actionLoading" @click="changeReviewStatus('pending')">撤回审核</el-button>
        </div>

        <el-form v-if="editMode" label-position="top" class="edit-form">
          <div class="form-grid"><el-form-item label="使用场景"><el-input v-model="usageScene" maxlength="255" placeholder="例如：商品首图、详情页、短视频投放" /></el-form-item><el-form-item label="评分"><el-rate v-model="score" clearable /></el-form-item></div>
          <el-form-item label="标签"><el-input v-model="tagsText" maxlength="660" placeholder="使用逗号分隔，最多 20 个" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="remark" type="textarea" :rows="3" maxlength="5000" show-word-limit /></el-form-item>
          <div class="save-row"><el-button type="primary" :loading="saving" @click="saveMetadata">保存素材信息</el-button></div>
        </el-form>

        <el-descriptions :column="2" border class="descriptions">
          <el-descriptions-item label="素材版本">v{{ selected.version_no }}</el-descriptions-item><el-descriptions-item label="并发版本">{{ selected.lock_version }}</el-descriptions-item>
          <el-descriptions-item label="来源方案">#{{ selected.creative_plan_id }}</el-descriptions-item><el-descriptions-item label="来源任务">{{ selected.generation_job_id ? `#${selected.generation_job_id}` : '—' }}</el-descriptions-item>
          <el-descriptions-item label="媒体格式">{{ selected.mime_type || '—' }}</el-descriptions-item><el-descriptions-item label="文件大小">{{ formatBytes(selected.file_size_bytes) }}</el-descriptions-item>
          <el-descriptions-item label="尺寸/时长"><span v-if="selected.width && selected.height">{{ selected.width }} × {{ selected.height }}</span><span v-else-if="selected.duration_sec">{{ selected.duration_sec }} 秒</span><span v-else>—</span></el-descriptions-item><el-descriptions-item label="生成模型">{{ selected.model_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="审核时间">{{ formatDate(selected.reviewed_at) }}</el-descriptions-item><el-descriptions-item label="同步时间">{{ formatDate(selected.synced_at) }}</el-descriptions-item>
        </el-descriptions>
        <section class="notes"><div><small>使用场景</small><p>{{ selected.usage_scene || '未设置' }}</p></div><div><small>备注</small><p>{{ selected.remark || '暂无备注' }}</p></div><div><small>SHA-256</small><code>{{ selected.checksum_sha256 || '—' }}</code></div></section>
      </div>
    </el-drawer>
  </section>
</template>

<style scoped>
.asset-panel{overflow:hidden;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:24px;border-bottom:1px solid var(--color-border);background:linear-gradient(135deg,#f8f0e5,#edf3ef)}.panel-head p,.drawer-title small{margin:0 0 7px;color:var(--color-accent);font-size:10px;font-weight:800;letter-spacing:.17em}.panel-head h2{margin:0;font-family:var(--font-display);font-size:28px;font-weight:500}.panel-head span{display:block;margin-top:7px;color:var(--color-muted);font-size:12px}.filters{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}.filters :deep(.el-select){width:135px}.asset-grid{display:grid;min-height:420px;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px;padding:20px}.asset-card{overflow:hidden;border:1px solid var(--color-border);border-radius:12px;background:#fffefa;cursor:pointer;transition:.18s ease}.asset-card:hover{transform:translateY(-2px);border-color:#91a898;box-shadow:0 10px 24px rgb(40 61 50 / 11%)}.media-placeholder{position:relative;display:grid;height:190px;place-items:center;background:linear-gradient(145deg,#e9eee9,#d7e1d9);color:#496252}.media-placeholder.type-video{background:linear-gradient(145deg,#272e2b,#121614);color:#d7e5d8}.media-placeholder.file-missing,.media-placeholder.file-invalid{background:#eee7e3;color:#976554}.media-placeholder>small{position:absolute;right:12px;bottom:10px;color:inherit;font-size:10px}.media-placeholder>span{position:absolute;top:10px;left:10px;display:flex;align-items:center;gap:4px;padding:5px 8px;border-radius:6px;background:#fff4ef;font-size:10px;font-weight:700}.asset-body{padding:15px}.asset-title{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.asset-title small{color:var(--color-muted);font-size:9px}.asset-title h3{margin:5px 0 10px;font-family:var(--font-display);font-size:19px;font-weight:500}.meta{display:flex;flex-wrap:wrap;gap:7px;color:var(--color-muted);font-size:9px}.tags{display:flex;min-height:24px;flex-wrap:wrap;gap:5px;margin:12px 0}.tags>span{color:var(--color-muted);font-size:10px}.score{display:flex;align-items:center;justify-content:space-between;border-top:1px dashed var(--color-border);padding-top:10px;color:var(--color-muted);font-size:11px}.score :deep(.el-rate){height:auto}.pager{display:flex;justify-content:flex-end;padding:0 20px 20px}.drawer-title{display:flex;width:100%;align-items:center;justify-content:space-between;padding-right:10px}.drawer-title h3{margin:4px 0 0;font-family:var(--font-display);font-size:24px;font-weight:500}.drawer-title>div:last-child{display:flex;gap:6px}.preview-stage{display:grid;min-height:340px;overflow:hidden;place-items:center;border-radius:12px;background:#171c1a}.preview-stage :deep(.el-image),.preview-stage video{width:100%;height:420px;object-fit:contain}.toolbar{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;margin:14px 0}.edit-form{margin:14px 0;padding:16px;border:1px solid var(--color-border);border-radius:10px;background:#faf8f2}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.save-row{display:flex;justify-content:flex-end}.descriptions{margin-top:15px}.notes{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}.notes>div{padding:13px;border:1px solid var(--color-border);border-radius:9px}.notes>div:last-child{grid-column:1/-1}.notes small{color:var(--color-muted);font-size:10px}.notes p{margin:7px 0 0;line-height:1.6}.notes code{display:block;overflow-wrap:anywhere;margin-top:7px;font-size:10px}@media(max-width:1100px){.asset-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.panel-head{flex-direction:column}.filters{width:100%;justify-content:flex-start}}@media(max-width:680px){.asset-grid{grid-template-columns:1fr;padding:12px}.filters :deep(.el-select){width:100%}.form-grid,.notes{grid-template-columns:1fr}.notes>div:last-child{grid-column:auto}.preview-stage :deep(.el-image),.preview-stage video{height:300px}}
</style>
