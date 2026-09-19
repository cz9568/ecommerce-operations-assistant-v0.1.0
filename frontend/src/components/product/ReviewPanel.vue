<script setup lang="ts">
import { CircleClose, DataLine, DocumentAdd, EditPen, MagicStick, Refresh, UploadFilled, View } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getAssets } from "../../api/assets"
import { getCreativePlans } from "../../api/creativePlans"
import { generateDiagnosis } from "../../api/diagnoses"
import { getApiErrorMessage } from "../../api/http"
import { getAdExperiments, getPromotionLinks } from "../../api/marketing"
import { createPerformanceRecord, generateReviewReport, getPerformanceRecords, getPerformanceSummary, getReviewReportRevisions, getReviewReports, updatePerformanceRecord, updateReviewReport, voidPerformanceRecord } from "../../api/performance"
import type { PerformancePayload } from "../../api/performance"
import { useAuthStore } from "../../stores/auth"
import type { AdExperiment, CreativePlan, GeneratedAsset, PerformanceRecord, PerformanceRecordStatus, PerformanceSummary, PromotionLink, ReviewReport, ReviewReportRevision } from "../../types/domain"
import { formatDate } from "../../utils/domain"

const props = defineProps<{ productId: number }>()
const emit = defineEmits<{ dirty: [value: boolean] }>()
const authStore = useAuthStore(); const route = useRoute(); const router = useRouter()
const activeSection = ref<"performance" | "reports">("performance")
const records = ref<PerformanceRecord[]>([]); const summary = ref<PerformanceSummary | null>(null)
const reports = ref<ReviewReport[]>([]); const current = ref<ReviewReport | null>(null)
const assets = ref<GeneratedAsset[]>([]); const links = ref<PromotionLink[]>([]); const experiments = ref<AdExperiment[]>([]); const plans = ref<CreativePlan[]>([])
const loading = ref(false); const saving = ref(false); const statusFilter = ref<PerformanceRecordStatus | "">("")
const recordOpen = ref(false); const editingRecord = ref<PerformanceRecord | null>(null)
const generateOpen = ref(false); const editReportOpen = ref(false); const revisionsOpen = ref(false); const revisions = ref<ReviewReportRevision[]>([])
const canWrite = computed(() => authStore.can("performance.write")); const canGenerate = computed(() => authStore.can("ai.generate"))
const recordForm = reactive({ period: [] as string[], impressions: 0, clicks: 0, conversions: 0, spend: 0, revenue: 0, creative_plan_id: undefined as number | undefined, generated_asset_id: undefined as number | undefined, promotion_link_id: undefined as number | undefined, experiment_id: undefined as number | undefined, notes: "" })
const reportForm = reactive({ period: [] as string[], notes: "" })
const reportEdit = reactive({ summary: "", core_insights: "", problem_assessment: "", next_actions: "" })
const reportSections = computed(() => current.value ? [["周期摘要", current.value.summary], ["核心洞察", current.value.core_insights.join("\n")], ["问题判断", current.value.problem_assessment.join("\n")], ["下一步动作", current.value.next_actions.join("\n")]] : [])

watch([recordOpen, generateOpen, editReportOpen], (states) => emit("dirty", states.some(Boolean)))
function percent(value: string | null): string { return value === null ? "—" : `${(Number(value) * 100).toFixed(2)}%` }
function metric(value: string | null): string { return value === null ? "—" : Number(value).toFixed(2) }
async function loadAll(selectNewest = false): Promise<void> {
  loading.value = true
  try {
    const [recordResult, totalResult, reportResult, assetResult, linkResult, experimentResult, mainPlans, videoPlans] = await Promise.all([
      getPerformanceRecords(props.productId, statusFilter.value), getPerformanceSummary(props.productId), getReviewReports(props.productId),
      getAssets(props.productId, { page: 1, page_size: 100 }), getPromotionLinks(props.productId), getAdExperiments(props.productId),
      getCreativePlans(props.productId, { plan_type: "main_image", page: 1, page_size: 100 }), getCreativePlans(props.productId, { plan_type: "video_script", page: 1, page_size: 100 }),
    ])
    records.value = recordResult.items; summary.value = totalResult; reports.value = reportResult.items; assets.value = assetResult.items; links.value = linkResult.items; experiments.value = experimentResult.items; plans.value = [...mainPlans.items, ...videoPlans.items]
    const requestedId = Number(route.query.review)
    const requested = Number.isInteger(requestedId) ? reports.value.find((item) => item.id === requestedId) : undefined
    if (requested) current.value = requested
    else if (selectNewest || !current.value || !reports.value.some((item) => item.id === current.value?.id)) current.value = reports.value[0] || null
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "经营数据与复盘加载失败")) }
  finally { loading.value = false }
}
function resetRecord(): void { Object.assign(recordForm, { period: [], impressions: 0, clicks: 0, conversions: 0, spend: 0, revenue: 0, creative_plan_id: undefined, generated_asset_id: undefined, promotion_link_id: undefined, experiment_id: undefined, notes: "" }) }
function openRecord(item?: PerformanceRecord): void {
  editingRecord.value = item || null; resetRecord()
  if (item) Object.assign(recordForm, { period: [item.period_start, item.period_end], impressions: item.impressions, clicks: item.clicks, conversions: item.conversions, spend: Number(item.spend), revenue: Number(item.revenue), creative_plan_id: item.creative_plan_id || undefined, generated_asset_id: item.generated_asset_id || undefined, promotion_link_id: item.promotion_link_id || undefined, experiment_id: item.experiment_id || undefined, notes: item.notes || "" })
  recordOpen.value = true
}
function performancePayload(): PerformancePayload | null {
  if (recordForm.period.length !== 2) { ElMessage.warning("请选择完整经营周期"); return null }
  if (recordForm.clicks > recordForm.impressions || recordForm.conversions > recordForm.clicks) { ElMessage.warning("指标关系必须满足：转化数 ≤ 点击数 ≤ 曝光数"); return null }
  return { period_start: recordForm.period[0], period_end: recordForm.period[1], impressions: recordForm.impressions, clicks: recordForm.clicks, conversions: recordForm.conversions, spend: recordForm.spend, revenue: recordForm.revenue, creative_plan_id: recordForm.creative_plan_id || null, generated_asset_id: recordForm.generated_asset_id || null, promotion_link_id: recordForm.promotion_link_id || null, experiment_id: recordForm.experiment_id || null, notes: recordForm.notes.trim() || null }
}
async function saveRecord(): Promise<void> {
  const payload = performancePayload(); if (!payload) return
  saving.value = true
  try { if (editingRecord.value) await updatePerformanceRecord(props.productId, editingRecord.value.id, { ...payload, expected_version: editingRecord.value.version_no }); else await createPerformanceRecord(props.productId, payload); recordOpen.value = false; await loadAll(); ElMessage.success(editingRecord.value ? "经营记录已更新" : "经营记录已创建") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "经营记录保存失败")) }
  finally { saving.value = false }
}
async function voidRecord(item: PerformanceRecord): Promise<void> {
  await ElMessageBox.confirm("作废后记录会保留审计信息，但不再参与汇总和复盘。", "作废经营记录", { type: "warning", confirmButtonText: "确认作废" })
  try { await voidPerformanceRecord(props.productId, item.id, item.version_no); await loadAll(); ElMessage.success("经营记录已作废") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "经营记录作废失败")) }
}
function editRecordRow(item: unknown): void { openRecord(item as PerformanceRecord) }
function voidRecordRow(item: unknown): void { void voidRecord(item as PerformanceRecord) }
function openGenerate(): void { reportForm.period = summary.value?.period_start && summary.value?.period_end ? [summary.value.period_start, summary.value.period_end] : []; reportForm.notes = ""; generateOpen.value = true }
async function createReport(): Promise<void> {
  if (reportForm.period.length !== 2) { ElMessage.warning("请选择复盘周期"); return }
  saving.value = true
  try { const created = await generateReviewReport(props.productId, { period_start: reportForm.period[0], period_end: reportForm.period[1], notes: reportForm.notes.trim() || undefined }); generateOpen.value = false; activeSection.value = "reports"; await loadAll(true); current.value = created; ElMessage.success("复盘报告已生成") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "复盘生成失败")) }
  finally { saving.value = false }
}
function openReportEdit(): void { if (!current.value) return; Object.assign(reportEdit, { summary: current.value.summary, core_insights: current.value.core_insights.join("\n"), problem_assessment: current.value.problem_assessment.join("\n"), next_actions: current.value.next_actions.join("\n") }); editReportOpen.value = true }
async function saveReport(): Promise<void> {
  if (!current.value || Object.values(reportEdit).some((value) => !value.trim())) { ElMessage.warning("四项复盘内容均不能为空"); return }
  saving.value = true
  try { const updated = await updateReviewReport(props.productId, current.value.id, { expected_version: current.value.version_no, ...reportEdit }); current.value = updated; reports.value = reports.value.map((item) => item.id === updated.id ? updated : item); editReportOpen.value = false; ElMessage.success("复盘报告已保存") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "复盘保存失败，请刷新后重试")) }
  finally { saving.value = false }
}
async function showRevisions(): Promise<void> { if (!current.value) return; try { revisions.value = await getReviewReportRevisions(props.productId, current.value.id); revisionsOpen.value = true } catch (error) { ElMessage.error(getApiErrorMessage(error, "版本历史加载失败")) } }
async function startNextRound(): Promise<void> {
  if (!current.value) return
  await ElMessageBox.confirm("将以这份复盘及其下一步动作为上下文生成新一轮商品诊断。", "开启下一轮诊断", { type: "warning", confirmButtonText: "确认生成" })
  saving.value = true
  try { const diagnosis = await generateDiagnosis(props.productId, { source_review_report_id: current.value.id, notes: `从复盘 #${current.value.id} 开启下一轮` }); await loadAll(); ElMessage.success(`新一轮诊断 #${diagnosis.id} 已生成`); await router.push({ name: "product-detail", params: { productId: props.productId, tab: "diagnosis" } }) }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "新一轮诊断生成失败")) }
  finally { saving.value = false }
}
function importNotice(): void { void router.push({ name: "imports", query: { type: "performance_records", product_id: String(props.productId) } }) }

onMounted(() => void loadAll(true))
watch(() => props.productId, () => { current.value = null; void loadAll(true) })
</script>

<template>
  <section class="review-panel">
    <header class="panel-head"><div><p>PERFORMANCE & REVIEW</p><h2>经营数据与运营复盘</h2><span>统一指标口径、冻结周期快照，并从复盘结论开启下一轮诊断。</span></div><div class="head-actions"><el-segmented v-model="activeSection" :options="[{ label: '经营数据', value: 'performance' }, { label: '复盘报告', value: 'reports' }]" /><el-button :icon="Refresh" :loading="loading" @click="loadAll()">刷新</el-button><el-button v-if="canWrite" :icon="UploadFilled" @click="importNotice">导入数据</el-button><el-button v-if="canWrite && activeSection === 'performance'" type="primary" :icon="DocumentAdd" @click="openRecord()">录入数据</el-button><el-button v-if="canGenerate && activeSection === 'reports'" type="primary" :icon="MagicStick" :disabled="!summary?.record_count" @click="openGenerate">生成复盘</el-button></div></header>

    <template v-if="activeSection === 'performance'">
      <div class="metrics" v-if="summary"><div><span>曝光</span><strong>{{ summary.impressions.toLocaleString() }}</strong></div><div><span>CTR</span><strong>{{ percent(summary.ctr) }}</strong><small>{{ summary.clicks.toLocaleString() }} 点击</small></div><div><span>转化率</span><strong>{{ percent(summary.conversion_rate) }}</strong><small>{{ summary.conversions.toLocaleString() }} 转化</small></div><div><span>花费 / 收入</span><strong>¥{{ Number(summary.spend).toFixed(2) }}</strong><small>收入 ¥{{ Number(summary.revenue).toFixed(2) }}</small></div><div><span>ROI</span><strong>{{ metric(summary.roi) }}</strong></div></div>
      <div class="record-toolbar"><el-select v-model="statusFilter" clearable placeholder="全部状态" @change="loadAll"><el-option label="有效" value="active" /><el-option label="已作废" value="voided" /></el-select><span>口径：CTR=点击/曝光，转化率=转化/点击，ROI=收入/花费；分母为 0 时显示为空。</span></div>
      <div v-loading="loading" class="table-wrap"><el-table :data="records" empty-text="暂无经营记录"><el-table-column label="周期" min-width="180"><template #default="{ row }">{{ row.period_start }} 至 {{ row.period_end }}</template></el-table-column><el-table-column prop="impressions" label="曝光" /><el-table-column prop="clicks" label="点击" /><el-table-column label="CTR"><template #default="{ row }">{{ percent(row.ctr) }}</template></el-table-column><el-table-column prop="conversions" label="转化" /><el-table-column label="转化率"><template #default="{ row }">{{ percent(row.conversion_rate) }}</template></el-table-column><el-table-column label="花费 / 收入" min-width="150"><template #default="{ row }">¥{{ row.spend }} / ¥{{ row.revenue }}</template></el-table-column><el-table-column label="ROI"><template #default="{ row }">{{ metric(row.roi) }}</template></el-table-column><el-table-column label="关联" min-width="150"><template #default="{ row }"><small>方案 #{{ row.creative_plan_id || '—' }} · 素材 #{{ row.generated_asset_id || '—' }}<br>链接 #{{ row.promotion_link_id || '—' }} · 实验 #{{ row.experiment_id || '—' }}</small></template></el-table-column><el-table-column label="状态"><template #default="{ row }"><el-tag :type="row.record_status === 'active' ? 'success' : 'info'">{{ row.record_status === 'active' ? '有效' : '已作废' }}</el-tag></template></el-table-column><el-table-column v-if="canWrite" label="操作" fixed="right" width="130"><template #default="{ row }"><el-button v-if="row.record_status === 'active'" text :icon="EditPen" @click="editRecordRow(row)">编辑</el-button><el-button v-if="row.record_status === 'active'" text type="danger" :icon="CircleClose" @click="voidRecordRow(row)">作废</el-button></template></el-table-column></el-table></div>
    </template>

    <div v-else v-loading="loading" class="report-workspace">
      <aside class="history"><div><strong>复盘历史</strong><span>{{ reports.length }} 份</span></div><button v-for="item in reports" :key="item.id" :class="{ active: current?.id === item.id }" @click="current = item"><span><b>#{{ item.id }}</b><el-tag size="small" effect="plain">v{{ item.version_no }}</el-tag></span><small>{{ item.period_start }} 至 {{ item.period_end }}</small></button><el-empty v-if="!reports.length" description="尚无复盘报告" :image-size="50" /></aside>
      <main class="report-result"><template v-if="current"><div class="report-head"><div><h3>运营复盘 #{{ current.id }}</h3><span>{{ current.period_start }} 至 {{ current.period_end }} · {{ current.provider_name }} / {{ current.model_name }}</span></div><div><el-button :icon="View" @click="showRevisions">版本历史</el-button><el-button v-if="canWrite" :icon="EditPen" @click="openReportEdit">编辑</el-button><el-button v-if="canGenerate" type="primary" :icon="DataLine" :loading="saving" @click="startNextRound">开启下一轮</el-button></div></div><div class="snapshot-strip"><span>经营记录 <b>{{ current.input_snapshot.records?.length || 0 }}</b></span><span>内容版本 <b>v{{ current.version_no }}</b></span><span>后续诊断 <b>{{ current.follow_up_diagnoses.length }}</b></span></div><div class="report-grid"><article v-for="section in reportSections" :key="String(section[0])"><small>{{ section[0] }}</small><p>{{ section[1] }}</p></article></div><div v-if="current.follow_up_diagnoses.length" class="follow-ups"><strong>已开启的后续诊断</strong><el-button v-for="item in current.follow_up_diagnoses" :key="item.id" text type="primary" @click="router.push({ name: 'product-detail', params: { productId, tab: 'diagnosis' } })">诊断 #{{ item.id }} · {{ formatDate(item.created_at) }}</el-button></div></template><el-empty v-else description="先录入经营数据，再生成第一份复盘报告" /></main>
    </div>

    <el-dialog v-model="recordOpen" :title="editingRecord ? '编辑经营记录' : '录入经营数据'" width="min(860px, 96vw)" :close-on-click-modal="!saving"><el-alert title="有效周期不能与本商品其他有效记录重叠；关联方案、素材、链接和实验必须属于当前商品。" type="info" show-icon :closable="false" /><el-form label-position="top" class="record-form"><el-form-item label="经营周期" required class="wide"><el-date-picker v-model="recordForm.period" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" /></el-form-item><el-form-item label="曝光数"><el-input-number v-model="recordForm.impressions" :min="0" /></el-form-item><el-form-item label="点击数"><el-input-number v-model="recordForm.clicks" :min="0" /></el-form-item><el-form-item label="转化数"><el-input-number v-model="recordForm.conversions" :min="0" /></el-form-item><el-form-item label="花费"><el-input-number v-model="recordForm.spend" :min="0" :precision="2" /></el-form-item><el-form-item label="收入"><el-input-number v-model="recordForm.revenue" :min="0" :precision="2" /></el-form-item><el-form-item label="关联创意方案"><el-select v-model="recordForm.creative_plan_id" clearable><el-option v-for="item in plans" :key="item.id" :label="`#${item.id} · ${item.title}`" :value="item.id" /></el-select></el-form-item><el-form-item label="关联素材"><el-select v-model="recordForm.generated_asset_id" clearable><el-option v-for="item in assets" :key="item.id" :label="`#${item.id} · ${item.asset_type}`" :value="item.id" /></el-select></el-form-item><el-form-item label="关联推广链接"><el-select v-model="recordForm.promotion_link_id" clearable><el-option v-for="item in links" :key="item.id" :label="`#${item.id} · ${item.link_name}`" :value="item.id" /></el-select></el-form-item><el-form-item label="关联实验"><el-select v-model="recordForm.experiment_id" clearable><el-option v-for="item in experiments" :key="item.id" :label="`#${item.id} · ${item.experiment_name}`" :value="item.id" /></el-select></el-form-item><el-form-item label="备注" class="wide"><el-input v-model="recordForm.notes" type="textarea" :rows="3" maxlength="5000" show-word-limit /></el-form-item></el-form><template #footer><el-button :disabled="saving" @click="recordOpen = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveRecord">保存记录</el-button></template></el-dialog>
    <el-dialog v-model="generateOpen" title="生成运营复盘" width="min(600px, 94vw)" :close-on-click-modal="!saving"><el-alert title="只会读取所选周期内完整落入周期的有效经营记录，并将输入快照永久保存。" type="info" show-icon :closable="false" /><el-form label-position="top" class="dialog-form"><el-form-item label="复盘周期" required><el-date-picker v-model="reportForm.period" type="daterange" value-format="YYYY-MM-DD" range-separator="至" /></el-form-item><el-form-item label="补充说明"><el-input v-model="reportForm.notes" type="textarea" :rows="4" maxlength="2000" show-word-limit /></el-form-item></el-form><template #footer><el-button :disabled="saving" @click="generateOpen = false">取消</el-button><el-button type="primary" :loading="saving" @click="createReport">生成复盘</el-button></template></el-dialog>
    <el-dialog v-model="editReportOpen" title="编辑复盘报告" width="min(820px, 96vw)" :close-on-click-modal="!saving"><el-alert title="每次保存都会创建不可变版本；原始模型输出和经营数据快照不会被覆盖。" type="warning" show-icon :closable="false" /><el-form label-position="top" class="report-edit"><el-form-item label="周期摘要"><el-input v-model="reportEdit.summary" type="textarea" :rows="3" maxlength="4000" /></el-form-item><el-form-item label="核心洞察"><el-input v-model="reportEdit.core_insights" type="textarea" :rows="3" maxlength="4000" /></el-form-item><el-form-item label="问题判断"><el-input v-model="reportEdit.problem_assessment" type="textarea" :rows="3" maxlength="4000" /></el-form-item><el-form-item label="下一步动作"><el-input v-model="reportEdit.next_actions" type="textarea" :rows="3" maxlength="4000" /></el-form-item></el-form><template #footer><el-button :disabled="saving" @click="editReportOpen = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveReport">保存新版本</el-button></template></el-dialog>
    <el-drawer v-model="revisionsOpen" title="复盘版本历史" size="min(720px, 94vw)"><el-timeline><el-timeline-item v-for="item in revisions" :key="item.id" :timestamp="formatDate(item.created_at)" placement="top"><el-card shadow="never"><template #header><strong>版本 v{{ item.version_no }}</strong></template><p>{{ item.summary }}</p><small>下一步：{{ item.next_actions.join('；') }}</small></el-card></el-timeline-item></el-timeline></el-drawer>
  </section>
</template>

<style scoped>
.review-panel{overflow:hidden;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:24px;border-bottom:1px solid var(--color-border);background:linear-gradient(135deg,#f6efe5,#edf4ef)}.panel-head p{margin:0 0 7px;color:var(--color-accent);font-size:10px;font-weight:800;letter-spacing:.17em}.panel-head h2{margin:0;font-family:var(--font-display);font-size:28px;font-weight:500}.panel-head span{display:block;margin-top:7px;color:var(--color-muted);font-size:12px}.head-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;border-bottom:1px solid var(--color-border);background:var(--color-border)}.metrics>div{display:flex;align-items:flex-start;flex-direction:column;padding:18px;background:#fffefa}.metrics span,.metrics small{color:var(--color-muted);font-size:10px}.metrics strong{margin:7px 0 4px;font-family:var(--font-display);font-size:25px;font-weight:500}.record-toolbar{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;background:#f8f7f2}.record-toolbar :deep(.el-select){width:130px}.record-toolbar span{color:var(--color-muted);font-size:10px}.table-wrap{min-height:420px;padding:0 20px 20px}.table-wrap small{color:var(--color-muted);line-height:1.6}.report-workspace{display:grid;min-height:600px;grid-template-columns:220px minmax(0,1fr)}.history{padding:14px;border-right:1px solid var(--color-border);background:#f8f7f2}.history>div{display:flex;justify-content:space-between;padding:7px}.history>div span{color:var(--color-muted);font-size:10px}.history button{display:flex;width:100%;flex-direction:column;gap:6px;margin-top:6px;padding:11px;border:1px solid transparent;border-radius:8px;background:transparent;text-align:left;cursor:pointer}.history button:hover,.history button.active{border-color:#d9cfc1;background:#fff}.history button span{display:flex;align-items:center;justify-content:space-between}.history button small{color:var(--color-muted);font-size:10px}.report-result{padding:23px}.report-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.report-head h3{margin:0;font-family:var(--font-display);font-size:25px;font-weight:500}.report-head span{display:block;margin-top:5px;color:var(--color-muted);font-size:10px}.snapshot-strip{display:flex;gap:8px;margin:16px 0}.snapshot-strip span{padding:7px 10px;border-radius:7px;background:#edf2ed;color:var(--color-muted);font-size:10px}.snapshot-strip b{color:var(--color-ink)}.report-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.report-grid article{padding:17px;border:1px solid var(--color-border);border-radius:10px;background:#fffefa}.report-grid article:last-child{background:#f0f5ef}.report-grid small{color:var(--color-accent);font-weight:700}.report-grid p{margin:11px 0 0;line-height:1.75;white-space:pre-wrap}.follow-ups{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin-top:15px;padding:12px;border-radius:8px;background:#f5f1e9}.record-form{display:grid;grid-template-columns:repeat(3,1fr);gap:0 14px;margin-top:18px}.record-form :deep(.el-select),.record-form :deep(.el-date-editor),.record-form :deep(.el-input-number){width:100%}.record-form .wide{grid-column:1/-1}.dialog-form{margin-top:18px}.dialog-form :deep(.el-date-editor){width:100%}.report-edit{display:grid;grid-template-columns:1fr 1fr;gap:0 14px;margin-top:18px}@media(max-width:1050px){.metrics{grid-template-columns:repeat(3,1fr)}.record-form{grid-template-columns:1fr 1fr}}@media(max-width:800px){.panel-head,.report-head,.record-toolbar{align-items:flex-start;flex-direction:column}.report-workspace{grid-template-columns:1fr}.history{display:flex;overflow-x:auto;border-right:0;border-bottom:1px solid var(--color-border)}.history button{min-width:175px}.report-grid,.report-edit{grid-template-columns:1fr}}@media(max-width:600px){.metrics,.record-form{grid-template-columns:1fr}.record-form .wide{grid-column:auto}.report-result{padding:14px}}
</style>
