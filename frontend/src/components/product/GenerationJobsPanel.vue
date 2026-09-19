<script setup lang="ts">
import { CircleClose, Refresh, RefreshRight, View } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import {
  cancelGenerationJob,
  getGenerationJob,
  getGenerationJobEvents,
  getGenerationJobs,
  retryGenerationJob,
} from "../../api/generationJobs"
import { getApiErrorMessage } from "../../api/http"
import { useAuthStore } from "../../stores/auth"
import type {
  GenerationJob,
  GenerationJobEvent,
  GenerationJobKind,
  GenerationJobStatus,
} from "../../types/domain"
import { formatDate } from "../../utils/domain"

const props = defineProps<{ productId: number }>()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const records = ref<GenerationJob[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const kindFilter = ref<GenerationJobKind | "">("")
const statusFilter = ref<GenerationJobStatus | "">("")
const loading = ref(false)
const refreshing = ref(false)
const loadError = ref("")
const detailDrawer = ref(false)
const detailLoading = ref(false)
const selectedJob = ref<GenerationJob | null>(null)
const events = ref<GenerationJobEvent[]>([])
const actionJobId = ref<number | null>(null)
const pollDelay = ref(5000)
let pollTimer: number | null = null

const statusLabels: Record<GenerationJobStatus, string> = {
  pending: "等待中",
  running: "生成中",
  succeeded: "已成功",
  failed: "失败",
  cancelled: "已取消",
  timeout: "已超时",
}
const kindLabels: Record<GenerationJobKind, string> = { image: "图片", video: "视频" }
const activeStatuses = new Set<GenerationJobStatus>(["pending", "running"])
const canOperate = computed(() => authStore.can("job.operate"))
const hasActiveTask = computed(() =>
  records.value.some((job) => activeStatuses.has(job.job_status))
  || Boolean(selectedJob.value && activeStatuses.has(selectedJob.value.job_status)),
)

function statusType(status: GenerationJobStatus): "success" | "warning" | "danger" | "info" | "primary" {
  if (status === "succeeded") return "success"
  if (status === "failed" || status === "timeout") return "danger"
  if (status === "pending") return "warning"
  if (status === "running") return "primary"
  return "info"
}
function canCancel(jobValue: unknown): boolean {
  const job = jobValue as GenerationJob
  return canOperate.value && activeStatuses.has(job.job_status)
}
function canRetry(jobValue: unknown): boolean {
  const job = jobValue as GenerationJob
  return canOperate.value
    && (job.job_status === "failed" || job.job_status === "timeout")
    && job.attempts < job.max_attempts
}
function planTitle(jobValue: unknown): string {
  const job = jobValue as GenerationJob
  const plan = job.input_snapshot.plan
  if (plan && typeof plan === "object" && "title" in plan) return String(plan.title || "未命名方案")
  return "未命名方案"
}
function kindLabel(jobValue: unknown): string {
  return kindLabels[(jobValue as GenerationJob).job_kind]
}
function jobStatusLabel(jobValue: unknown): string {
  return statusLabels[(jobValue as GenerationJob).job_status]
}
function resultAssets(job: GenerationJob): Array<Record<string, unknown>> {
  const assets = job.result?.assets
  return Array.isArray(assets) ? assets.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : []
}
function eventLabel(event: GenerationJobEvent): string {
  const labels: Record<string, string> = {
    "job.created": "任务创建",
    "job.claimed": "Worker 领取",
    "job.poll_claimed": "继续轮询",
    "job.retry_scheduled": "自动重试排队",
    "job.manual_retry_scheduled": "人工重试排队",
    "job.lock_recovered": "任务锁恢复",
    "job.timeout": "任务超时",
    "job.cancelled": "任务取消",
    "job.succeeded": "生成成功",
    "job.dead_lettered": "最终失败",
    "provider.submitting": "提交生成服务",
    "provider.submitted": "外部任务已受理",
    "provider.polling": "外部任务处理中",
    "provider.poll_failed": "轮询暂时失败",
  }
  return labels[event.event_type] || event.event_type
}
function clearPollTimer(): void {
  if (pollTimer !== null) window.clearTimeout(pollTimer)
  pollTimer = null
}
function schedulePoll(delay = pollDelay.value): void {
  clearPollTimer()
  if (!hasActiveTask.value || document.hidden) return
  pollTimer = window.setTimeout(() => void poll(), delay)
}

async function loadRecords(silent = false): Promise<boolean> {
  if (silent) refreshing.value = true
  else loading.value = true
  try {
    const result = await getGenerationJobs(props.productId, {
      job_kind: kindFilter.value || undefined,
      job_status: statusFilter.value || undefined,
      page: page.value,
      page_size: pageSize,
    })
    records.value = result.items
    total.value = result.total
    loadError.value = ""
    return true
  } catch (error) {
    loadError.value = getApiErrorMessage(error, "生成任务加载失败")
    return false
  } finally {
    loading.value = false
    refreshing.value = false
  }
}
async function loadDetail(jobId: number, silent = false): Promise<boolean> {
  if (!silent) detailLoading.value = true
  try {
    const [job, timeline] = await Promise.all([
      getGenerationJob(props.productId, jobId),
      getGenerationJobEvents(props.productId, jobId),
    ])
    selectedJob.value = job
    events.value = timeline
    records.value = records.value.map((item) => item.id === job.id ? job : item)
    return true
  } catch (error) {
    if (!silent) ElMessage.error(getApiErrorMessage(error, "任务详情加载失败"))
    return false
  } finally {
    detailLoading.value = false
  }
}
async function poll(): Promise<void> {
  if (document.hidden) return
  const listOk = await loadRecords(true)
  let detailOk = true
  if (selectedJob.value && activeStatuses.has(selectedJob.value.job_status)) {
    detailOk = await loadDetail(selectedJob.value.id, true)
  }
  pollDelay.value = listOk && detailOk ? 5000 : Math.min(pollDelay.value * 2, 30000)
  schedulePoll()
}
async function refreshAll(): Promise<void> {
  clearPollTimer()
  pollDelay.value = 5000
  await loadRecords()
  if (selectedJob.value) await loadDetail(selectedJob.value.id)
  schedulePoll()
}
async function filterChanged(): Promise<void> {
  page.value = 1
  await refreshAll()
}
async function changePage(value: number): Promise<void> {
  page.value = value
  await refreshAll()
}
async function openDetail(jobOrId: unknown): Promise<void> {
  const typedJob = jobOrId as GenerationJob
  const jobId = typeof jobOrId === "number" ? jobOrId : typedJob.id
  if (typeof jobOrId !== "number") selectedJob.value = typedJob
  detailDrawer.value = true
  await router.replace({ query: { ...route.query, job: String(jobId) } })
  await loadDetail(jobId)
  schedulePoll()
}
async function closeDetail(): Promise<void> {
  selectedJob.value = null
  events.value = []
  const query = { ...route.query }
  delete query.job
  await router.replace({ query })
  schedulePoll()
}

async function cancelJob(jobValue: unknown): Promise<void> {
  const job = jobValue as GenerationJob
  const warning = job.job_status === "running"
    ? "任务已提交到外部平台。本系统会立即停止跟踪和落库，但供应商侧生成可能仍会继续。请输入取消原因（选填）。"
    : "取消后该任务不会被 Worker 执行。请输入取消原因（选填）。"
  try {
    const result = await ElMessageBox.prompt(warning, `取消${kindLabels[job.job_kind]}任务 #${job.id}`, {
      type: "warning",
      confirmButtonText: "确认取消",
      cancelButtonText: "返回",
      inputPlaceholder: "例如：方案需要重新调整",
      inputValidator: (value: string) => value.length <= 500 || "取消原因不能超过 500 个字符",
    })
    actionJobId.value = job.id
    const updated = await cancelGenerationJob(props.productId, job.id, {
      expected_version: job.version_no,
      reason: result.value?.trim() || undefined,
    })
    records.value = records.value.map((item) => item.id === updated.id ? updated : item)
    if (selectedJob.value?.id === updated.id) {
      selectedJob.value = updated
      events.value = await getGenerationJobEvents(props.productId, updated.id)
    }
    ElMessage.success("任务已取消")
  } catch (error) {
    if (error === "cancel" || error === "close") return
    ElMessage.error(getApiErrorMessage(error, "取消失败，任务状态可能已变化"))
    await refreshAll()
  } finally {
    actionJobId.value = null
    schedulePoll()
  }
}
async function retryJob(jobValue: unknown): Promise<void> {
  const job = jobValue as GenerationJob
  try {
    const result = await ElMessageBox.prompt(
      `将使用原方案 v${job.creative_plan_version_no} 的不可变输入快照重新排队。剩余可提交次数：${job.max_attempts - job.attempts}。`,
      `重试${kindLabels[job.job_kind]}任务 #${job.id}`,
      {
        type: "info",
        confirmButtonText: "确认重试",
        cancelButtonText: "返回",
        inputPlaceholder: "重试原因（选填）",
        inputValidator: (value: string) => value.length <= 500 || "重试原因不能超过 500 个字符",
      },
    )
    actionJobId.value = job.id
    const updated = await retryGenerationJob(props.productId, job.id, {
      expected_version: job.version_no,
      reason: result.value?.trim() || undefined,
    })
    records.value = records.value.map((item) => item.id === updated.id ? updated : item)
    if (selectedJob.value?.id === updated.id) {
      selectedJob.value = updated
      events.value = await getGenerationJobEvents(props.productId, updated.id)
    }
    ElMessage.success("任务已重新排队")
  } catch (error) {
    if (error === "cancel" || error === "close") return
    ElMessage.error(getApiErrorMessage(error, "重试失败，任务状态可能已变化"))
    await refreshAll()
  } finally {
    actionJobId.value = null
    schedulePoll()
  }
}
function handleVisibilityChange(): void {
  if (document.hidden) clearPollTimer()
  else if (hasActiveTask.value) {
    pollDelay.value = 5000
    schedulePoll(0)
  }
}

onMounted(async () => {
  document.addEventListener("visibilitychange", handleVisibilityChange)
  await loadRecords()
  const routeJobId = Number(route.query.job)
  if (Number.isInteger(routeJobId) && routeJobId > 0) await openDetail(routeJobId)
  schedulePoll()
})
onBeforeUnmount(() => {
  clearPollTimer()
  document.removeEventListener("visibilitychange", handleVisibilityChange)
})
watch(() => props.productId, async () => {
  clearPollTimer()
  detailDrawer.value = false
  selectedJob.value = null
  events.value = []
  page.value = 1
  await loadRecords()
  schedulePoll()
})
</script>

<template>
  <section class="jobs-panel">
    <header class="panel-head">
      <div>
        <p>ASYNC MEDIA PIPELINE</p>
        <h2>图片与视频生成任务</h2>
        <span>运行中任务每 5 秒自动刷新；请求失败时逐步退避至 30 秒，进入终态后停止轮询。</span>
      </div>
      <div class="filters">
        <el-select v-model="kindFilter" clearable placeholder="全部类型" @change="filterChanged">
          <el-option label="图片" value="image" /><el-option label="视频" value="video" />
        </el-select>
        <el-select v-model="statusFilter" clearable placeholder="全部状态" @change="filterChanged">
          <el-option v-for="(label, status) in statusLabels" :key="status" :label="label" :value="status" />
        </el-select>
        <el-button :icon="Refresh" :loading="loading || refreshing" @click="refreshAll">刷新</el-button>
      </div>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" show-icon :closable="false">
      <template #default><el-button link type="primary" @click="refreshAll">重新加载</el-button></template>
    </el-alert>
    <el-alert
      v-else-if="hasActiveTask"
      class="polling-hint"
      title="存在进行中的任务，页面正在自动更新"
      type="info"
      show-icon
      :closable="false"
    />

    <el-table v-loading="loading" :data="records" class="jobs-table" row-key="id">
      <el-table-column label="任务" min-width="210">
        <template #default="{ row }">
          <button class="job-link" type="button" @click="openDetail(row)">#{{ row.id }} · {{ planTitle(row) }}</button>
          <small>方案 #{{ row.creative_plan_id }} / v{{ row.creative_plan_version_no }}</small>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="82">
        <template #default="{ row }">{{ kindLabel(row) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }"><el-tag :type="statusType(row.job_status)" effect="plain">{{ jobStatusLabel(row) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="进度" min-width="150">
        <template #default="{ row }"><el-progress :percentage="row.progress_percent" :status="row.job_status === 'failed' || row.job_status === 'timeout' ? 'exception' : row.job_status === 'succeeded' ? 'success' : undefined" /></template>
      </el-table-column>
      <el-table-column label="尝试" width="80">
        <template #default="{ row }">{{ row.attempts }}/{{ row.max_attempts }}</template>
      </el-table-column>
      <el-table-column label="更新时间" width="175">
        <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" :icon="View" @click="openDetail(row)">详情</el-button>
          <el-button v-if="canCancel(row)" link type="danger" :icon="CircleClose" :loading="actionJobId === row.id" @click="cancelJob(row)">取消</el-button>
          <el-button v-if="canRetry(row)" link type="primary" :icon="RefreshRight" :loading="actionJobId === row.id" @click="retryJob(row)">重试</el-button>
          <small v-else-if="canOperate && (row.job_status === 'failed' || row.job_status === 'timeout') && row.attempts >= row.max_attempts" class="limit-hint">已达上限</small>
        </template>
      </el-table-column>
      <template #empty><el-empty description="尚无图片或视频生成任务" /></template>
    </el-table>
    <el-pagination
      v-if="total > pageSize"
      class="pager"
      background
      layout="prev,pager,next,total"
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      @update:current-page="changePage"
    />

    <el-drawer v-model="detailDrawer" size="min(780px, 96vw)" @closed="closeDetail">
      <template #header>
        <div v-if="selectedJob" class="drawer-title">
          <div><small>GENERATION JOB</small><h3>任务 #{{ selectedJob.id }}</h3></div>
          <el-tag :type="statusType(selectedJob.job_status)" effect="plain">{{ statusLabels[selectedJob.job_status] }}</el-tag>
        </div>
      </template>
      <div v-if="selectedJob" v-loading="detailLoading" class="job-detail">
        <div class="detail-actions">
          <el-button :icon="Refresh" @click="loadDetail(selectedJob.id)">刷新详情</el-button>
          <el-button v-if="canCancel(selectedJob)" type="danger" plain :icon="CircleClose" :loading="actionJobId === selectedJob.id" @click="cancelJob(selectedJob)">取消任务</el-button>
          <el-button v-if="canRetry(selectedJob)" type="primary" :icon="RefreshRight" :loading="actionJobId === selectedJob.id" @click="retryJob(selectedJob)">重新排队</el-button>
        </div>
        <el-alert v-if="selectedJob.job_status === 'running'" title="取消运行中任务会立即阻止本地结果落库，但外部供应商任务可能仍继续执行。" type="warning" show-icon :closable="false" />
        <el-alert v-if="selectedJob.error_code || selectedJob.error_message" class="error-alert" :title="selectedJob.error_message || '生成任务执行失败'" :description="selectedJob.error_code || undefined" type="error" show-icon :closable="false" />

        <el-descriptions :column="2" border class="descriptions">
          <el-descriptions-item label="生成类型">{{ kindLabels[selectedJob.job_kind] }}</el-descriptions-item>
          <el-descriptions-item label="进度">{{ selectedJob.progress_percent }}%</el-descriptions-item>
          <el-descriptions-item label="方案版本">#{{ selectedJob.creative_plan_id }} / v{{ selectedJob.creative_plan_version_no }}</el-descriptions-item>
          <el-descriptions-item label="尝试次数">{{ selectedJob.attempts }} / {{ selectedJob.max_attempts }}</el-descriptions-item>
          <el-descriptions-item label="Provider">{{ selectedJob.provider_name || '尚未提交' }}</el-descriptions-item>
          <el-descriptions-item label="外部任务号">{{ selectedJob.external_job_id || '—' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDate(selectedJob.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ formatDate(selectedJob.finished_at) }}</el-descriptions-item>
        </el-descriptions>

        <section class="snapshot-card">
          <small>IMMUTABLE INPUT</small>
          <h4>{{ planTitle(selectedJob) }}</h4>
          <p>任务始终使用创建时锁定的方案 v{{ selectedJob.creative_plan_version_no }}，后续方案编辑不会改变本次输入。</p>
          <code>{{ JSON.stringify(selectedJob.input_snapshot.parameters || {}, null, 2) }}</code>
        </section>

        <section v-if="resultAssets(selectedJob).length" class="result-card">
          <small>GENERATED RESULT</small><h4>生成结果</h4>
          <div v-for="(asset, index) in resultAssets(selectedJob)" :key="index" class="asset-row">
            <span>{{ String(asset.media_type || '媒体文件') }}</span>
            <span v-if="asset.width && asset.height">{{ asset.width }} × {{ asset.height }}</span>
            <span v-if="asset.duration_seconds">{{ asset.duration_seconds }} 秒</span>
            <a v-if="asset.url" :href="String(asset.url)" target="_blank" rel="noopener noreferrer">打开临时结果</a>
          </div>
        </section>

        <section class="timeline-card">
          <div class="timeline-head"><div><small>EVENT TIMELINE</small><h4>事件时间线</h4></div><span>{{ events.length }} 条</span></div>
          <el-timeline v-if="events.length">
            <el-timeline-item v-for="event in events" :key="event.id" :timestamp="formatDate(event.created_at)" placement="top">
              <strong>{{ eventLabel(event) }}</strong><p>{{ event.event_message || '状态已更新' }}</p>
              <details v-if="Object.keys(event.event_data).length"><summary>事件数据</summary><pre>{{ JSON.stringify(event.event_data, null, 2) }}</pre></details>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无事件" :image-size="70" />
        </section>
      </div>
    </el-drawer>
  </section>
</template>

<style scoped>
.jobs-panel{overflow:hidden;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:24px;border-bottom:1px solid var(--color-border);background:linear-gradient(135deg,#f7f2e9,#edf3ef)}.panel-head p,.snapshot-card>small,.result-card>small,.timeline-head small,.drawer-title small{margin:0 0 7px;color:var(--color-accent);font-size:10px;font-weight:800;letter-spacing:.17em}.panel-head h2{margin:0;font-family:var(--font-display);font-size:28px;font-weight:500}.panel-head span{display:block;margin-top:7px;color:var(--color-muted);font-size:12px}.filters{display:flex;gap:8px}.filters :deep(.el-select){width:125px}.polling-hint{border-radius:0}.jobs-table{width:100%}.job-link{display:block;max-width:100%;overflow:hidden;padding:0;border:0;background:none;color:var(--color-ink);cursor:pointer;font-weight:700;text-align:left;text-overflow:ellipsis;white-space:nowrap}.job-link:hover{color:var(--color-accent)}.jobs-table small{display:block;margin-top:5px;color:var(--color-muted)}.limit-hint{display:inline!important;margin-left:9px!important}.pager{display:flex;justify-content:flex-end;padding:18px}.drawer-title{display:flex;width:100%;align-items:center;justify-content:space-between;padding-right:10px}.drawer-title h3{margin:3px 0 0;font-family:var(--font-display);font-size:25px;font-weight:500}.detail-actions{display:flex;justify-content:flex-end;gap:8px;margin-bottom:14px}.error-alert{margin-top:12px}.descriptions{margin-top:16px}.snapshot-card,.result-card,.timeline-card{margin-top:16px;padding:17px;border:1px solid var(--color-border);border-radius:11px;background:#fffefa}.snapshot-card h4,.result-card h4,.timeline-head h4{margin:5px 0 7px;font-family:var(--font-display);font-size:21px;font-weight:500}.snapshot-card p{color:var(--color-muted);font-size:12px;line-height:1.65}.snapshot-card code{display:block;overflow-x:auto;padding:11px;border-radius:8px;background:#17221e;color:#deeadf;font-size:11px;white-space:pre}.asset-row{display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px dashed var(--color-border);font-size:12px}.asset-row a{margin-left:auto;color:var(--color-accent);font-weight:700}.timeline-head{display:flex;align-items:flex-start;justify-content:space-between}.timeline-head>span{color:var(--color-muted);font-size:11px}.timeline-card :deep(.el-timeline){padding-left:7px}.timeline-card strong{font-size:13px}.timeline-card p{margin:5px 0;color:var(--color-muted);font-size:12px;line-height:1.55}.timeline-card details{font-size:11px}.timeline-card summary{color:var(--color-accent);cursor:pointer}.timeline-card pre{overflow-x:auto;padding:9px;border-radius:7px;background:#f3f1ea;font-size:10px}@media(max-width:820px){.panel-head{flex-direction:column}.filters{width:100%;flex-wrap:wrap}.jobs-table{min-width:900px}.jobs-panel{overflow-x:auto}}@media(max-width:520px){.filters :deep(.el-select){width:100%}.detail-actions{align-items:stretch;flex-direction:column}.asset-row{align-items:flex-start;flex-direction:column}.asset-row a{margin-left:0}}
</style>
