<script setup lang="ts">
import { Clock, Link, Plus, Refresh, Search } from "@element-plus/icons-vue"
import axios from "axios"
import { ElMessage, ElMessageBox } from "element-plus"
import { computed, onMounted, reactive, ref, watch } from "vue"

import {
  applyMonitorSnapshot,
  applyParseTask,
  archiveCompetitor,
  createCompetitor,
  createParseTask,
  getCompetitorMonitor,
  getCompetitors,
  getMonitorSnapshots,
  getParseTasks,
  runCompetitorMonitor,
  runParseTask,
  saveCompetitorMonitor,
  updateCompetitor,
} from "../../api/competitors"
import type { CompetitorField, CompetitorPayload } from "../../api/competitors"
import { getApiErrorMessage } from "../../api/http"
import { useAuthStore } from "../../stores/auth"
import type { Competitor, CompetitorFieldSource, CompetitorMonitor, EntityStatus, LinkParseTask, MonitorSnapshot, ParseTaskStatus, StorePlatform } from "../../types/domain"
import { formatDate, formatMoney, platformLabels, platformOptions } from "../../utils/domain"
import FormDialog from "../common/FormDialog.vue"

const props = defineProps<{ productId: number }>()
const emit = defineEmits<{ dirty: [value: boolean] }>()
const authStore = useAuthStore(); const canWrite = computed(() => authStore.can("competitor.write"))
const activeTab = ref("competitors"); const competitors = ref<Competitor[]>([]); const total = ref(0); const page = ref(1); const loading = ref(false)
const query = ref(""); const statusFilter = ref<EntityStatus | "">(""); const platformFilter = ref<StorePlatform | "">("")
const tasks = ref<LinkParseTask[]>([]); const taskTotal = ref(0); const taskPage = ref(1); const taskStatus = ref<ParseTaskStatus | "">(""); const taskLoading = ref(false)
const competitorDialog = ref(false); const parseDialog = ref(false); const applyDialog = ref(false); const monitorDrawer = ref(false); const saving = ref(false); const parsingId = ref<number | null>(null)
const editingCompetitor = ref<Competitor | null>(null); const currentTask = ref<LinkParseTask | null>(null); const selectedCompetitor = ref<Competitor | null>(null); const monitor = ref<CompetitorMonitor | null>(null); const snapshots = ref<MonitorSnapshot[]>([]); const snapshotTotal = ref(0); const snapshotLoading = ref(false)
const form = reactive<CompetitorPayload>({ name: "", platform: "tmall", url: null, price: null, sales_hint: null, title: null, main_image: null, selling_points: null, review_keywords: null, status: "active" })
const parseForm = reactive({ source_url: "", competitor_id: undefined as number | undefined })
const applyForm = reactive({ fields: [] as CompetitorField[], name: "", platform: "tmall" as StorePlatform })
const monitorForm = reactive({ monitor_status: "active" as "active" | "paused", interval_minutes: 1440 })
const sourceLabels: Record<CompetitorFieldSource, string> = { manual: "手工", parsed: "解析", monitor: "监控" }
const taskStatusLabels: Record<ParseTaskStatus, string> = { pending: "待执行", running: "执行中", succeeded: "成功", failed: "失败", cancelled: "已取消", timeout: "超时" }
const fieldLabels: Record<CompetitorField, string> = { name: "名称", url: "链接", price: "价格", sales_hint: "销量提示", title: "标题", main_image: "主图", selling_points: "卖点", review_keywords: "评价关键词" }
const applyFieldOptions = computed(() => {
  const result = currentTask.value?.result
  if (!result) return []
  return (Object.keys(fieldLabels) as CompetitorField[]).filter((field) => field === "url" || field === "name" || result[field as keyof typeof result] !== null)
})

watch([competitorDialog, parseDialog, applyDialog], (values) => emit("dirty", values.some(Boolean)))
async function loadCompetitors(): Promise<void> {
  loading.value = true
  try { const result = await getCompetitors(props.productId, { page: page.value, page_size: 20, q: query.value.trim() || undefined, status: statusFilter.value || undefined, platform: platformFilter.value || undefined }); competitors.value = result.items; total.value = result.total }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "竞品列表加载失败")) }
  finally { loading.value = false }
}
async function loadTasks(): Promise<void> {
  taskLoading.value = true
  try { const result = await getParseTasks(props.productId, { page: taskPage.value, page_size: 20, status: taskStatus.value || undefined }); tasks.value = result.items; taskTotal.value = result.total }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "解析任务加载失败")) }
  finally { taskLoading.value = false }
}
function openCompetitor(item?: Competitor): void {
  editingCompetitor.value = item || null
  Object.assign(form, item ? { name: item.name, platform: item.platform, url: item.url, price: item.price === null ? null : Number(item.price), sales_hint: item.sales_hint, title: item.title, main_image: item.main_image, selling_points: item.selling_points, review_keywords: item.review_keywords, status: item.status } : { name: "", platform: "tmall", url: null, price: null, sales_hint: null, title: null, main_image: null, selling_points: null, review_keywords: null, status: "active" })
  competitorDialog.value = true
}
async function saveCompetitor(): Promise<void> {
  if (!form.name.trim()) { ElMessage.warning("请输入竞品名称"); return }
  saving.value = true
  try {
    if (editingCompetitor.value) await updateCompetitor(props.productId, editingCompetitor.value.id, form)
    else await createCompetitor(props.productId, form)
    competitorDialog.value = false; await loadCompetitors(); ElMessage.success(editingCompetitor.value ? "竞品已更新" : "竞品已创建")
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "竞品保存失败")) }
  finally { saving.value = false }
}
async function removeCompetitor(item: Competitor): Promise<void> {
  await ElMessageBox.confirm("停用后历史解析任务和监控快照仍会保留。", `停用竞品 · ${item.name}`, { type: "warning", confirmButtonText: "确认停用" })
  try { await archiveCompetitor(props.productId, item.id); await loadCompetitors(); ElMessage.success("竞品已停用") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "竞品停用失败")) }
}
function openParse(item?: Competitor): void {
  parseForm.source_url = item?.url || ""; parseForm.competitor_id = item?.id; parseDialog.value = true
}
async function createAndRunParse(): Promise<void> {
  if (!parseForm.source_url.trim()) { ElMessage.warning("请输入公开商品链接"); return }
  saving.value = true
  try {
    const created = await createParseTask(props.productId, { source_url: parseForm.source_url.trim(), competitor_id: parseForm.competitor_id })
    parseDialog.value = false; const result = await executeTask(created)
    if (result.task_status === "succeeded") openApply(result)
    else { activeTab.value = "tasks"; ElMessage.error(result.error_message || "公开链接解析失败") }
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "解析任务创建失败")) }
  finally { saving.value = false; await loadTasks() }
}
async function executeTask(task: LinkParseTask): Promise<LinkParseTask> {
  parsingId.value = task.id
  try { return await runParseTask(props.productId, task.id) }
  finally { parsingId.value = null }
}
async function retryTask(task: LinkParseTask): Promise<void> {
  try { const result = await executeTask(task); await loadTasks(); if (result.task_status === "succeeded") openApply(result); else ElMessage.error(result.error_message || "解析仍然失败") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "解析任务执行失败")) }
}
function openApply(task: LinkParseTask): void {
  currentTask.value = task; applyForm.fields = applyFieldOptions.value.filter((field) => field !== "name"); applyForm.name = task.result?.title || ""; const target = competitors.value.find((item) => item.id === task.competitor_id); applyForm.platform = target?.platform || "tmall"; applyDialog.value = true
}
async function applyTask(): Promise<void> {
  if (!currentTask.value || !applyForm.fields.length) { ElMessage.warning("请至少选择一个回填字段"); return }
  saving.value = true
  try { await applyParseTask(props.productId, currentTask.value.id, { competitor_id: currentTask.value.competitor_id || undefined, fields: applyForm.fields, name: currentTask.value.competitor_id ? undefined : applyForm.name, platform: currentTask.value.competitor_id ? undefined : applyForm.platform }); applyDialog.value = false; await Promise.all([loadCompetitors(), loadTasks()]); ElMessage.success("已按选择字段采用解析结果") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "解析结果回填失败")) }
  finally { saving.value = false }
}
function sourceOf(item: Competitor, field: string): string { const source = item.field_sources[field]; return source ? sourceLabels[source] : "未标记" }
async function openMonitor(item: Competitor): Promise<void> {
  selectedCompetitor.value = item; monitor.value = null; snapshots.value = []; monitorDrawer.value = true
  try { monitor.value = await getCompetitorMonitor(props.productId, item.id); Object.assign(monitorForm, { monitor_status: monitor.value.monitor_status === "paused" ? "paused" : "active", interval_minutes: monitor.value.interval_minutes }); await loadSnapshots() }
  catch (error) { if (!axios.isAxiosError(error) || error.response?.status !== 404) ElMessage.error(getApiErrorMessage(error, "监控配置加载失败")); else Object.assign(monitorForm, { monitor_status: "active", interval_minutes: 1440 }) }
}
async function saveMonitor(): Promise<void> {
  if (!selectedCompetitor.value) return
  saving.value = true
  try { monitor.value = await saveCompetitorMonitor(props.productId, selectedCompetitor.value.id, monitorForm); await loadSnapshots(); ElMessage.success("监控配置已保存") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "监控配置保存失败")) }
  finally { saving.value = false }
}
async function runMonitorNow(): Promise<void> {
  if (!selectedCompetitor.value || !monitor.value) return
  saving.value = true
  try { monitor.value = await runCompetitorMonitor(props.productId, selectedCompetitor.value.id); await loadSnapshots(); if (monitor.value.last_error_code) ElMessage.error(monitor.value.last_error || "本次监控失败") ; else ElMessage.success("监控快照已生成") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "监控执行失败")) }
  finally { saving.value = false }
}
async function loadSnapshots(): Promise<void> {
  if (!selectedCompetitor.value || !monitor.value) return
  snapshotLoading.value = true
  try { const result = await getMonitorSnapshots(props.productId, selectedCompetitor.value.id, { page: 1, page_size: 50 }); snapshots.value = result.items; snapshotTotal.value = result.total }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "监控快照加载失败")) }
  finally { snapshotLoading.value = false }
}
async function adoptSnapshot(snapshot: MonitorSnapshot): Promise<void> {
  if (!selectedCompetitor.value) return
  const fields = (snapshot.changed_fields.length ? snapshot.changed_fields : ["price", "sales_hint", "title", "main_image", "selling_points", "review_keywords"]) as CompetitorField[]
  try { await applyMonitorSnapshot(props.productId, selectedCompetitor.value.id, snapshot.id, fields); await loadCompetitors(); ElMessage.success("已采用这份监控快照中的变化字段") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "快照回填失败")) }
}
function search(): void { page.value = 1; void loadCompetitors() }
onMounted(() => { void Promise.all([loadCompetitors(), loadTasks()]) })
watch(() => props.productId, () => { page.value = 1; taskPage.value = 1; void Promise.all([loadCompetitors(), loadTasks()]) })
</script>

<template>
  <section class="panel">
    <div class="panel-title"><div><h3>竞品与公开链接</h3><p>手工数据不会被解析或监控结果自动覆盖，只有人工确认后才回填</p></div><div class="actions"><el-button v-if="canWrite" :icon="Link" @click="openParse()">解析公开链接</el-button><el-button v-if="canWrite" type="primary" :icon="Plus" @click="openCompetitor()">新增竞品</el-button></div></div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="竞品列表" name="competitors">
        <div class="toolbar"><el-input v-model="query" clearable placeholder="搜索竞品名称或标题" :prefix-icon="Search" @keyup.enter="search" /><el-select v-model="platformFilter" clearable placeholder="全部平台"><el-option v-for="item in platformOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select><el-select v-model="statusFilter" clearable placeholder="全部状态"><el-option label="启用" value="active" /><el-option label="停用" value="inactive" /></el-select><el-button type="primary" plain :icon="Search" @click="search">查询</el-button><el-button :icon="Refresh" @click="loadCompetitors">刷新</el-button></div>
        <el-table v-loading="loading" :data="competitors"><el-table-column label="竞品" min-width="230"><template #default="scope"><div class="competitor-cell"><el-image v-if="scope.row.main_image" :src="scope.row.main_image" fit="cover" /><span v-else>竞</span><div><strong>{{ scope.row.name }}</strong><small>{{ platformLabels[scope.row.platform as StorePlatform] }} · {{ scope.row.title || '未填写标题' }}</small></div></div></template></el-table-column><el-table-column label="价格" width="130"><template #default="scope"><div>{{ formatMoney(scope.row.price) }}</div><small class="source">{{ sourceOf(scope.row as Competitor, 'price') }}</small></template></el-table-column><el-table-column label="销量提示" min-width="130"><template #default="scope"><div>{{ scope.row.sales_hint || '—' }}</div><small class="source">{{ sourceOf(scope.row as Competitor, 'sales_hint') }}</small></template></el-table-column><el-table-column label="最近解析" min-width="165"><template #default="scope">{{ formatDate(scope.row.last_parsed_at, '尚未解析') }}</template></el-table-column><el-table-column label="状态" width="90"><template #default="scope"><el-tag :type="scope.row.status === 'active' ? 'success' : 'info'">{{ scope.row.status === 'active' ? '启用' : '停用' }}</el-tag></template></el-table-column><el-table-column label="操作" min-width="250" fixed="right"><template #default="scope"><el-button link type="primary" @click="openMonitor(scope.row as Competitor)">监控</el-button><template v-if="canWrite"><el-button link :disabled="!scope.row.url" @click="openParse(scope.row as Competitor)">解析</el-button><el-button link @click="openCompetitor(scope.row as Competitor)">编辑</el-button><el-button v-if="scope.row.status === 'active'" link type="danger" @click="removeCompetitor(scope.row as Competitor)">停用</el-button></template></template></el-table-column></el-table>
        <el-empty v-if="!competitors.length && !loading" description="尚未录入竞品" :image-size="60" /><el-pagination v-if="total > 20" class="pager" background layout="prev,pager,next" :current-page="page" :page-size="20" :total="total" @update:current-page="(value:number) => { page = value; loadCompetitors() }" />
      </el-tab-pane>
      <el-tab-pane label="解析任务" name="tasks">
        <div class="task-toolbar"><el-select v-model="taskStatus" clearable placeholder="全部状态" @change="taskPage = 1; loadTasks()"><el-option v-for="(label,key) in taskStatusLabels" :key="key" :label="label" :value="key" /></el-select><el-button :icon="Refresh" @click="loadTasks">刷新</el-button></div>
        <el-table v-loading="taskLoading" :data="tasks"><el-table-column label="链接" min-width="260"><template #default="scope"><el-link :href="scope.row.source_url" target="_blank" type="primary" class="url-link">{{ scope.row.source_url }}</el-link><div class="subtle">尝试 {{ scope.row.attempts }}/{{ scope.row.max_attempts }}</div></template></el-table-column><el-table-column label="状态" width="100"><template #default="scope"><el-tag :type="scope.row.task_status === 'succeeded' ? 'success' : scope.row.task_status === 'failed' ? 'danger' : 'warning'">{{ taskStatusLabels[scope.row.task_status as ParseTaskStatus] }}</el-tag></template></el-table-column><el-table-column label="结果或错误" min-width="250"><template #default="scope"><span v-if="scope.row.task_status === 'succeeded'">{{ scope.row.result?.title || '已提取公开字段' }}</span><span v-else-if="scope.row.error_message" class="error-text">{{ scope.row.error_message }}（{{ scope.row.error_code }}）</span><span v-else class="subtle">等待执行</span></template></el-table-column><el-table-column label="完成时间" min-width="165"><template #default="scope">{{ formatDate(scope.row.finished_at) }}</template></el-table-column><el-table-column v-if="canWrite" label="操作" width="150"><template #default="scope"><el-button v-if="scope.row.task_status === 'succeeded'" link type="primary" @click="openApply(scope.row as LinkParseTask)">选择回填</el-button><el-button v-else-if="scope.row.task_status === 'failed' && scope.row.attempts < scope.row.max_attempts" link :loading="parsingId === scope.row.id" @click="retryTask(scope.row as LinkParseTask)">重试</el-button></template></el-table-column></el-table>
        <el-empty v-if="!tasks.length && !taskLoading" description="尚无公开链接解析任务" :image-size="60" />
      </el-tab-pane>
    </el-tabs>

    <FormDialog v-model="competitorDialog" :title="editingCompetitor ? '编辑竞品' : '新增竞品'" :loading="saving" width="760px" @confirm="saveCompetitor"><el-form :model="form" label-position="top"><div class="form-grid"><el-form-item label="竞品名称" required><el-input v-model="form.name" /></el-form-item><el-form-item label="平台"><el-select v-model="form.platform" style="width:100%"><el-option v-for="item in platformOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></div><el-form-item label="公开商品链接"><el-input v-model="form.url" placeholder="仅支持配置白名单内的公开 HTTP(S) 链接" /></el-form-item><div class="form-grid"><el-form-item label="价格"><el-input-number v-model="form.price" :min="0" :precision="2" style="width:100%" /></el-form-item><el-form-item label="销量提示"><el-input v-model="form.sales_hint" /></el-form-item></div><el-form-item label="公开标题"><el-input v-model="form.title" /></el-form-item><el-form-item label="主图地址"><el-input v-model="form.main_image" /></el-form-item><el-form-item label="卖点"><el-input v-model="form.selling_points" type="textarea" :rows="3" /></el-form-item><el-form-item label="评价关键词"><el-input v-model="form.review_keywords" type="textarea" :rows="2" /></el-form-item><el-form-item label="状态"><el-radio-group v-model="form.status"><el-radio-button value="active">启用</el-radio-button><el-radio-button value="inactive">停用</el-radio-button></el-radio-group></el-form-item></el-form></FormDialog>
    <FormDialog v-model="parseDialog" title="解析公开商品链接" :loading="saving" @confirm="createAndRunParse"><el-alert title="只读取白名单域名公开提供的 HTML 元数据；登录、验证码、风控或访问拒绝会明确失败，不会尝试绕过。" type="info" :closable="false" /><el-form label-position="top" class="dialog-form"><el-form-item label="目标竞品（选填）"><el-select v-model="parseForm.competitor_id" clearable filterable style="width:100%"><el-option v-for="item in competitors" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="公开商品链接" required><el-input v-model="parseForm.source_url" /></el-form-item></el-form></FormDialog>
    <FormDialog v-model="applyDialog" title="选择要采用的解析字段" :loading="saving" width="680px" @confirm="applyTask"><el-alert title="未勾选的手工字段会保持原值，不会被解析结果覆盖。" type="warning" :closable="false" /><el-form label-position="top" class="dialog-form"><template v-if="currentTask && !currentTask.competitor_id"><div class="form-grid"><el-form-item label="新竞品名称"><el-input v-model="applyForm.name" /></el-form-item><el-form-item label="平台"><el-select v-model="applyForm.platform" style="width:100%"><el-option v-for="item in platformOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></div></template><el-form-item label="回填字段"><el-checkbox-group v-model="applyForm.fields" class="field-checks"><el-checkbox v-for="field in applyFieldOptions" :key="field" :value="field">{{ fieldLabels[field] }}</el-checkbox></el-checkbox-group></el-form-item><div v-if="currentTask?.result" class="parse-preview"><div v-for="field in applyFieldOptions.filter(item => !['name','url'].includes(item))" :key="field"><small>{{ fieldLabels[field] }}</small><span>{{ currentTask.result[field as keyof typeof currentTask.result] || '—' }}</span></div></div></el-form></FormDialog>
    <el-drawer v-model="monitorDrawer" :title="`竞品监控 · ${selectedCompetitor?.name || ''}`" size="min(820px, 94vw)"><el-alert v-if="!selectedCompetitor?.url" title="请先为竞品填写公开链接，再启用监控。" type="warning" :closable="false" /><div class="monitor-config"><el-select v-model="monitorForm.monitor_status"><el-option label="启用" value="active" /><el-option label="暂停" value="paused" /></el-select><el-select v-model="monitorForm.interval_minutes"><el-option label="每小时" :value="60" /><el-option label="每 6 小时" :value="360" /><el-option label="每天" :value="1440" /><el-option label="每周" :value="10080" /></el-select><el-button v-if="canWrite" type="primary" :loading="saving" :disabled="!selectedCompetitor?.url" @click="saveMonitor">保存配置</el-button><el-button v-if="canWrite && monitor" :icon="Clock" :loading="saving" @click="runMonitorNow">立即执行</el-button></div><div v-if="monitor" class="monitor-state"><span>状态：{{ monitor.monitor_status }}</span><span>下次运行：{{ formatDate(monitor.next_run_at) }}</span><span>连续失败：{{ monitor.consecutive_failures }}</span><span>最近成功：{{ formatDate(monitor.last_success_at) }}</span></div><el-alert v-if="monitor?.last_error" :title="`${monitor.last_error}（${monitor.last_error_code}）`" type="error" :closable="false" /><h4>监控快照（{{ snapshotTotal }}）</h4><el-table v-loading="snapshotLoading" :data="snapshots"><el-table-column label="时间" min-width="160"><template #default="scope">{{ formatDate(scope.row.created_at) }}</template></el-table-column><el-table-column label="结果" width="90"><template #default="scope"><el-tag :type="scope.row.is_success ? 'success' : 'danger'">{{ scope.row.is_success ? '成功' : '失败' }}</el-tag></template></el-table-column><el-table-column label="价格" width="110"><template #default="scope">{{ formatMoney(scope.row.price) }}</template></el-table-column><el-table-column label="变化字段" min-width="180"><template #default="scope"><span v-if="scope.row.changed_fields.length">{{ scope.row.changed_fields.map((field:string) => fieldLabels[field as CompetitorField] || field).join('、') }}</span><span v-else class="subtle">无变化</span></template></el-table-column><el-table-column label="标题或错误" min-width="220"><template #default="scope"><span v-if="scope.row.is_success">{{ scope.row.title || '—' }}</span><span v-else class="error-text">{{ scope.row.error_message }}</span></template></el-table-column><el-table-column v-if="canWrite" label="操作" width="90"><template #default="scope"><el-button v-if="scope.row.is_success" link type="primary" @click="adoptSnapshot(scope.row as MonitorSnapshot)">采用变化</el-button></template></el-table-column></el-table><el-empty v-if="monitor && !snapshots.length && !snapshotLoading" description="尚无监控快照" /></el-drawer>
  </section>
</template>

<style scoped>
.panel{padding:22px;border:1px solid var(--color-border);border-radius:12px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.panel-title{display:flex;gap:20px;align-items:flex-start;justify-content:space-between;margin-bottom:10px}.panel-title h3{margin:0;font-family:var(--font-display);font-size:22px;font-weight:500}.panel-title p{margin:5px 0 0;color:var(--color-muted);font-size:12px}.actions{display:flex;gap:8px}.toolbar{display:grid;grid-template-columns:minmax(220px,1fr) 130px 120px auto auto;gap:10px;margin-bottom:16px}.competitor-cell{display:flex;gap:11px;align-items:center}.competitor-cell>span,.competitor-cell :deep(.el-image){display:grid;width:42px;height:42px;flex:0 0 auto;place-items:center;border-radius:9px;background:#efe9df;color:#9a5b3d;font-weight:800}.competitor-cell div{display:flex;overflow:hidden;flex-direction:column}.competitor-cell strong,.competitor-cell small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.competitor-cell small,.subtle,.source{margin-top:3px;color:var(--color-muted);font-size:11px}.source{color:#9a654d}.task-toolbar{display:flex;gap:10px;margin-bottom:16px}.url-link{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.error-text{color:#ba3d32;font-size:12px}.pager{display:flex;justify-content:flex-end;margin-top:16px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.dialog-form{margin-top:18px}.field-checks{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.parse-preview{display:grid;grid-template-columns:1fr 1fr;gap:8px}.parse-preview div{display:flex;min-width:0;flex-direction:column;padding:10px;border-radius:8px;background:#f4f2eb}.parse-preview small{color:var(--color-muted)}.parse-preview span{overflow:hidden;margin-top:5px;text-overflow:ellipsis;white-space:nowrap}.monitor-config{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}.monitor-state{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}.monitor-state span{padding:7px 10px;border-radius:7px;background:#f2f3ef;color:var(--color-muted);font-size:12px}h4{margin:24px 0 12px;font-family:var(--font-display);font-size:20px;font-weight:500}
@media(max-width:800px){.toolbar{grid-template-columns:1fr 1fr}.field-checks{grid-template-columns:1fr 1fr}}@media(max-width:560px){.panel-title{flex-direction:column}.actions{width:100%;flex-wrap:wrap}.toolbar,.form-grid,.parse-preview{grid-template-columns:1fr}}
</style>
