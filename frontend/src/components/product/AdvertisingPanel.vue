<script setup lang="ts">
import { CircleCheck, CircleClose, EditPen, MagicStick, Refresh, SetUp } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { computed, onMounted, reactive, ref, watch } from "vue"

import { getAssets } from "../../api/assets"
import { getApiErrorMessage } from "../../api/http"
import { confirmAdRecommendation, generateAdExperiment, generateAdRecommendation, getAdExperiments, getAdRecommendations, getPromotionLinks, updateAdExperiment, updateAdRecommendation } from "../../api/marketing"
import { useAuthStore } from "../../stores/auth"
import type { AdExperiment, AdExperimentStatus, AdRecommendation, GeneratedAsset, PromotionLink } from "../../types/domain"
import { formatDate } from "../../utils/domain"

const props = defineProps<{ productId: number }>()
const emit = defineEmits<{ dirty: [value: boolean] }>()
const authStore = useAuthStore()
const recommendations = ref<AdRecommendation[]>([])
const experiments = ref<AdExperiment[]>([])
const assets = ref<GeneratedAsset[]>([])
const links = ref<PromotionLink[]>([])
const current = ref<AdRecommendation | null>(null)
const loading = ref(false)
const actionLoading = ref(false)
const generateOpen = ref(false)
const confirmOpen = ref(false)
const editRecommendationOpen = ref(false)
const experimentOpen = ref(false)
const editExperimentOpen = ref(false)
const confirmationAction = ref<"confirmed" | "rejected">("confirmed")
const confirmationRemark = ref("")
const selectedExperiment = ref<AdExperiment | null>(null)
const canGenerate = computed(() => authStore.can("ai.generate"))
const canConfirm = computed(() => authStore.can("ad.confirm"))
const canExperiment = computed(() => authStore.can("experiment.write"))
const recommendationForm = reactive({ asset_ids: [] as number[], link_ids: [] as number[], notes: "" })
const experimentForm = reactive({ recommendation_id: 0, related_asset_id: 0, related_link_id: 0, experiment_name: "", budget_amount: 0 })
const editForm = reactive({ experiment_name: "", target_text: "", audience_text: "", budget_amount: 0, success_metric_text: "", hypothesis_text: "" })
const recommendationEditForm = reactive({ strategy_summary: "", objective: "", target_audience: "", budget_plan: "", creative_test_plan: "", bidding_strategy: "", risks: "", next_actions: "" })
const statusLabels: Record<AdExperimentStatus, string> = { draft: "草稿", confirmed: "已确认", running: "进行中", finished: "已完成", cancelled: "已取消" }
const recommendationLabels = { pending: "待确认", confirmed: "已确认", rejected: "已驳回" }
const sections = computed(() => current.value ? [
  ["策略摘要", current.value.summary_text], ["本轮目标", current.value.objective_text],
  ["人群建议", current.value.audience_segments], ["预算建议", current.value.budget_plan],
  ["素材测试", current.value.creative_tests], ["出价策略", current.value.bid_strategy],
  ["风险控制", current.value.risk_controls], ["下一步动作", current.value.next_steps],
] : [])

watch([generateOpen, confirmOpen, editRecommendationOpen, experimentOpen, editExperimentOpen], (states) => emit("dirty", states.some(Boolean)))
function textValue(value: unknown): string {
  if (typeof value === "string") return value
  if (Array.isArray(value)) return value.map(textValue).filter(Boolean).join("\n")
  if (value && typeof value === "object") return Object.values(value).map(textValue).filter(Boolean).join("\n")
  return value == null ? "—" : String(value)
}
async function loadAll(selectNewest = false): Promise<void> {
  loading.value = true
  try {
    const [recResult, expResult, assetResult, linkResult] = await Promise.all([
      getAdRecommendations(props.productId), getAdExperiments(props.productId),
      getAssets(props.productId, { review_status: "approved", file_status: "available", page: 1, page_size: 100 }),
      getPromotionLinks(props.productId, "active"),
    ])
    recommendations.value = recResult.items; experiments.value = expResult.items; assets.value = assetResult.items; links.value = linkResult.items
    if (selectNewest || !current.value || !recommendations.value.some((item) => item.id === current.value?.id)) current.value = recommendations.value[0] || null
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "投放工作区加载失败")) }
  finally { loading.value = false }
}
function openGenerate(): void { Object.assign(recommendationForm, { asset_ids: [], link_ids: [], notes: "" }); generateOpen.value = true }
async function createRecommendation(): Promise<void> {
  if (!recommendationForm.asset_ids.length || !recommendationForm.link_ids.length) { ElMessage.warning("至少选择一份已审核素材和一个有效推广链接"); return }
  actionLoading.value = true
  try {
    const created = await generateAdRecommendation(props.productId, { asset_ids: recommendationForm.asset_ids, link_ids: recommendationForm.link_ids, notes: recommendationForm.notes.trim() || undefined })
    generateOpen.value = false; await loadAll(true); current.value = created; ElMessage.success("投放建议已生成，等待人工确认")
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "投放建议生成失败")) }
  finally { actionLoading.value = false }
}
function openConfirmation(action: "confirmed" | "rejected"): void { confirmationAction.value = action; confirmationRemark.value = ""; confirmOpen.value = true }
function openRecommendationEdit(): void {
  if (!current.value) return
  Object.assign(recommendationEditForm, { strategy_summary: current.value.summary_text, objective: current.value.objective_text, target_audience: textValue(current.value.audience_segments), budget_plan: textValue(current.value.budget_plan), creative_test_plan: textValue(current.value.creative_tests), bidding_strategy: textValue(current.value.bid_strategy), risks: textValue(current.value.risk_controls), next_actions: textValue(current.value.next_steps) })
  editRecommendationOpen.value = true
}
async function saveRecommendation(): Promise<void> {
  if (!current.value || Object.values(recommendationEditForm).some((value) => !value.trim())) { ElMessage.warning("八项建议内容均不能为空"); return }
  actionLoading.value = true
  try {
    const updated = await updateAdRecommendation(props.productId, current.value.id, { expected_version: current.value.version_no, ...recommendationEditForm })
    current.value = updated; recommendations.value = recommendations.value.map((item) => item.id === updated.id ? updated : item); editRecommendationOpen.value = false; ElMessage.success("投放建议已保存")
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "投放建议保存失败，请刷新后重试")) }
  finally { actionLoading.value = false }
}
async function submitConfirmation(): Promise<void> {
  if (!current.value) return
  const actionText = confirmationAction.value === "confirmed" ? "确认" : "驳回"
  await ElMessageBox.confirm(`${actionText}后建议内容将锁定，且操作不可撤回。系统不会自动执行真实投放。`, `${actionText}投放建议`, { type: "warning", confirmButtonText: `确认${actionText}` })
  actionLoading.value = true
  try {
    const updated = await confirmAdRecommendation(props.productId, current.value.id, { expected_version: current.value.version_no, confirm_status: confirmationAction.value, remark: confirmationRemark.value.trim() || undefined })
    current.value = updated; recommendations.value = recommendations.value.map((item) => item.id === updated.id ? updated : item); confirmOpen.value = false; ElMessage.success(`投放建议已${actionText}`)
  } catch (error) { ElMessage.error(getApiErrorMessage(error, `${actionText}失败`)) }
  finally { actionLoading.value = false }
}
function openExperiment(recommendation?: AdRecommendation): void {
  const source = recommendation || recommendations.value.find((item) => item.confirm_status === "confirmed")
  if (!source) { ElMessage.warning("请先确认一份投放建议"); return }
  const snapshotAsset = Number(source.input_snapshot.approved_assets?.[0]?.id || assets.value[0]?.id || 0)
  const snapshotLink = Number(source.input_snapshot.promotion_links?.[0]?.id || links.value[0]?.id || 0)
  Object.assign(experimentForm, { recommendation_id: source.id, related_asset_id: snapshotAsset, related_link_id: snapshotLink, experiment_name: `投放实验 #${source.id}`, budget_amount: 0 })
  experimentOpen.value = true
}
async function createExperiment(): Promise<void> {
  if (!experimentForm.related_asset_id || !experimentForm.related_link_id) { ElMessage.warning("请选择实验素材和推广链接"); return }
  actionLoading.value = true
  try { await generateAdExperiment(props.productId, experimentForm); experimentOpen.value = false; await loadAll(); ElMessage.success("实验草稿已创建") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "实验创建失败")) }
  finally { actionLoading.value = false }
}
function openEditExperiment(item: AdExperiment): void {
  selectedExperiment.value = item; Object.assign(editForm, { experiment_name: item.experiment_name, target_text: item.target_text || "", audience_text: item.audience_text || "", budget_amount: Number(item.budget_amount), success_metric_text: item.success_metric_text || "", hypothesis_text: item.hypothesis_text || "" }); editExperimentOpen.value = true
}
async function saveExperiment(): Promise<void> {
  if (!selectedExperiment.value) return
  actionLoading.value = true
  try { await updateAdExperiment(props.productId, selectedExperiment.value.id, { expected_version: selectedExperiment.value.version_no, ...editForm }); editExperimentOpen.value = false; await loadAll(); ElMessage.success("实验计划已保存") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "实验计划保存失败")) }
  finally { actionLoading.value = false }
}
function nextActions(status: AdExperimentStatus): AdExperimentStatus[] {
  return { draft: ["confirmed", "cancelled"], confirmed: ["running", "cancelled"], running: ["finished", "cancelled"], finished: [], cancelled: [] }[status] as AdExperimentStatus[]
}
async function changeExperimentStatus(item: AdExperiment, status: AdExperimentStatus): Promise<void> {
  const label = statusLabels[status]
  await ElMessageBox.confirm(`确认将实验状态更新为“${label}”？该操作只记录计划状态，不会操作广告平台或预算。`, "更新实验状态", { type: "warning", confirmButtonText: "确认更新" })
  try { await updateAdExperiment(props.productId, item.id, { expected_version: item.version_no, experiment_status: status }); await loadAll(); ElMessage.success(`实验已更新为${label}`) }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "实验状态更新失败")) }
}

onMounted(() => void loadAll())
watch(() => props.productId, () => { current.value = null; void loadAll(true) })
</script>

<template>
  <section class="ads-panel">
    <header class="panel-head"><div><p>AD RECOMMENDATION & EXPERIMENT</p><h2>投放建议与人工实验</h2><span>基于已审核素材和有效链接生成建议；所有确认与实验状态均需人工操作。</span></div><div class="head-actions"><el-button :icon="Refresh" :loading="loading" @click="loadAll()">刷新</el-button><el-button v-if="canGenerate" type="primary" :icon="MagicStick" :disabled="!assets.length || !links.length" @click="openGenerate">生成投放建议</el-button><el-button v-if="canExperiment" :icon="SetUp" @click="openExperiment()">新建实验</el-button></div></header>
    <el-alert v-if="!assets.length || !links.length" :title="`生成前还需准备：${!assets.length ? '至少一份已审核素材' : ''}${!assets.length && !links.length ? '、' : ''}${!links.length ? '至少一个启用推广链接' : ''}`" type="warning" show-icon :closable="false" />
    <div v-loading="loading" class="workspace">
      <aside class="history"><div class="aside-title"><strong>建议历史</strong><span>{{ recommendations.length }} 份</span></div><button v-for="item in recommendations" :key="item.id" :class="{ active: current?.id === item.id }" @click="current = item"><span><b>#{{ item.id }}</b><el-tag size="small" :type="item.confirm_status === 'confirmed' ? 'success' : item.confirm_status === 'rejected' ? 'danger' : 'warning'">{{ recommendationLabels[item.confirm_status] }}</el-tag></span><small>{{ formatDate(item.created_at) }}</small></button><el-empty v-if="!recommendations.length" description="暂无建议" :image-size="50" /></aside>
      <main class="recommendation">
        <template v-if="current"><div class="result-head"><div><h3>投放建议 #{{ current.id }}</h3><span>{{ current.provider_name }} · {{ current.model_name }} · {{ current.prompt_version }}</span></div><div v-if="current.confirm_status === 'pending' && canConfirm"><el-button :icon="EditPen" @click="openRecommendationEdit">编辑</el-button><el-button type="danger" plain :icon="CircleClose" @click="openConfirmation('rejected')">驳回</el-button><el-button type="success" :icon="CircleCheck" @click="openConfirmation('confirmed')">人工确认</el-button></div><el-button v-else-if="current.confirm_status === 'confirmed' && canExperiment" type="primary" plain :icon="SetUp" @click="openExperiment(current)">生成实验计划</el-button></div><el-alert v-if="!current.input_snapshot.latest_diagnosis" title="生成时没有商品诊断，建议结合后续经营数据复核结论。" type="warning" show-icon :closable="false" /><div class="section-grid"><article v-for="section in sections" :key="String(section[0])"><small>{{ section[0] }}</small><p>{{ textValue(section[1]) }}</p></article></div><div v-if="current.confirm_status !== 'pending'" class="confirmation"><strong>{{ recommendationLabels[current.confirm_status] }}</strong><span>{{ current.confirmed_at ? formatDate(current.confirmed_at) : '' }} · {{ current.confirm_remark || '无备注' }}</span></div></template><el-empty v-else description="生成第一份投放建议后会显示在这里" /></main>
    </div>
    <section class="experiments"><div class="section-title"><div><p>EXPERIMENT PLANS</p><h3>实验计划</h3></div><span>状态流：草稿 → 已确认 → 进行中 → 已完成；非终态可取消。</span></div><div class="experiment-grid"><article v-for="item in experiments" :key="item.id"><div><small>#{{ item.id }} · 建议 #{{ item.recommendation_id }}</small><el-tag>{{ statusLabels[item.experiment_status] }}</el-tag></div><h4>{{ item.experiment_name }}</h4><p>{{ item.hypothesis_text || '未填写实验假设' }}</p><dl><div><dt>预算上限</dt><dd>¥ {{ item.budget_amount }}</dd></div><div><dt>素材 / 链接</dt><dd>#{{ item.related_asset_id }} / #{{ item.related_link_id }}</dd></div></dl><footer><el-button v-if="canExperiment && item.experiment_status === 'draft'" text :icon="EditPen" @click="openEditExperiment(item)">编辑</el-button><el-button v-for="status in nextActions(item.experiment_status)" :key="status" text :type="status === 'cancelled' ? 'danger' : 'primary'" @click="changeExperimentStatus(item, status)">{{ statusLabels[status] }}</el-button></footer></article><el-empty v-if="!experiments.length" description="暂无实验计划" /></div></section>

    <el-dialog v-model="generateOpen" title="生成投放建议" width="min(700px, 95vw)" :close-on-click-modal="!actionLoading"><el-alert title="只生成结构化建议，不会创建广告计划、扣费或修改预算。" type="info" show-icon :closable="false" /><el-form label-position="top" class="dialog-form"><el-form-item label="已审核素材" required><el-select v-model="recommendationForm.asset_ids" multiple placeholder="选择素材"><el-option v-for="item in assets" :key="item.id" :label="`#${item.id} · ${item.asset_type === 'image' ? '图片' : '视频'} · ${item.usage_scene || '未设置场景'}`" :value="item.id" /></el-select></el-form-item><el-form-item label="有效推广链接" required><el-select v-model="recommendationForm.link_ids" multiple placeholder="选择链接"><el-option v-for="item in links" :key="item.id" :label="`#${item.id} · ${item.link_name}`" :value="item.id" /></el-select></el-form-item><el-form-item label="补充说明"><el-input v-model="recommendationForm.notes" type="textarea" :rows="3" maxlength="2000" show-word-limit /></el-form-item></el-form><template #footer><el-button :disabled="actionLoading" @click="generateOpen = false">取消</el-button><el-button type="primary" :loading="actionLoading" @click="createRecommendation">生成并保存</el-button></template></el-dialog>
    <el-dialog v-model="confirmOpen" :title="confirmationAction === 'confirmed' ? '人工确认投放建议' : '驳回投放建议'" width="min(560px, 94vw)"><el-form label-position="top"><el-form-item label="确认备注"><el-input v-model="confirmationRemark" type="textarea" :rows="4" maxlength="2000" show-word-limit /></el-form-item></el-form><template #footer><el-button @click="confirmOpen = false">取消</el-button><el-button :type="confirmationAction === 'confirmed' ? 'success' : 'danger'" :loading="actionLoading" @click="submitConfirmation">{{ confirmationAction === 'confirmed' ? '确认建议' : '确认驳回' }}</el-button></template></el-dialog>
    <el-dialog v-model="editRecommendationOpen" title="编辑待确认建议" width="min(840px, 96vw)" :close-on-click-modal="!actionLoading"><el-alert title="保存会增加内容版本；人工确认或驳回后内容将永久锁定。" type="warning" show-icon :closable="false" /><el-form label-position="top" class="dialog-form form-grid"><el-form-item label="策略摘要"><el-input v-model="recommendationEditForm.strategy_summary" type="textarea" :rows="3" maxlength="4000" /></el-form-item><el-form-item label="本轮目标"><el-input v-model="recommendationEditForm.objective" type="textarea" :rows="3" maxlength="2000" /></el-form-item><el-form-item label="人群建议"><el-input v-model="recommendationEditForm.target_audience" type="textarea" :rows="3" maxlength="4000" /></el-form-item><el-form-item label="预算建议"><el-input v-model="recommendationEditForm.budget_plan" type="textarea" :rows="3" maxlength="4000" /></el-form-item><el-form-item label="素材测试"><el-input v-model="recommendationEditForm.creative_test_plan" type="textarea" :rows="3" maxlength="4000" /></el-form-item><el-form-item label="出价策略"><el-input v-model="recommendationEditForm.bidding_strategy" type="textarea" :rows="3" maxlength="4000" /></el-form-item><el-form-item label="风险控制"><el-input v-model="recommendationEditForm.risks" type="textarea" :rows="3" maxlength="4000" /></el-form-item><el-form-item label="下一步动作"><el-input v-model="recommendationEditForm.next_actions" type="textarea" :rows="3" maxlength="4000" /></el-form-item></el-form><template #footer><el-button :disabled="actionLoading" @click="editRecommendationOpen = false">取消</el-button><el-button type="primary" :loading="actionLoading" @click="saveRecommendation">保存建议</el-button></template></el-dialog>
    <el-dialog v-model="experimentOpen" title="从已确认建议生成实验" width="min(680px, 95vw)"><el-alert title="实验仅是可追踪的人工计划，不会向广告平台提交或修改任何预算。" type="warning" show-icon :closable="false" /><el-form label-position="top" class="dialog-form form-grid"><el-form-item label="实验名称"><el-input v-model="experimentForm.experiment_name" maxlength="255" /></el-form-item><el-form-item label="预算上限"><el-input-number v-model="experimentForm.budget_amount" :min="0" :precision="2" :step="100" /></el-form-item><el-form-item label="已审核素材" required><el-select v-model="experimentForm.related_asset_id"><el-option v-for="item in assets" :key="item.id" :label="`#${item.id} · ${item.usage_scene || item.asset_type}`" :value="item.id" /></el-select></el-form-item><el-form-item label="有效推广链接" required><el-select v-model="experimentForm.related_link_id"><el-option v-for="item in links" :key="item.id" :label="`#${item.id} · ${item.link_name}`" :value="item.id" /></el-select></el-form-item></el-form><template #footer><el-button @click="experimentOpen = false">取消</el-button><el-button type="primary" :loading="actionLoading" @click="createExperiment">创建实验草稿</el-button></template></el-dialog>
    <el-dialog v-model="editExperimentOpen" title="编辑实验草稿" width="min(760px, 95vw)"><el-form label-position="top" class="dialog-form form-grid"><el-form-item label="实验名称"><el-input v-model="editForm.experiment_name" /></el-form-item><el-form-item label="预算上限"><el-input-number v-model="editForm.budget_amount" :min="0" :precision="2" /></el-form-item><el-form-item label="实验目标"><el-input v-model="editForm.target_text" type="textarea" :rows="3" /></el-form-item><el-form-item label="目标人群"><el-input v-model="editForm.audience_text" type="textarea" :rows="3" /></el-form-item><el-form-item label="成功指标"><el-input v-model="editForm.success_metric_text" type="textarea" :rows="3" /></el-form-item><el-form-item label="实验假设"><el-input v-model="editForm.hypothesis_text" type="textarea" :rows="3" /></el-form-item></el-form><template #footer><el-button @click="editExperimentOpen = false">取消</el-button><el-button type="primary" :loading="actionLoading" @click="saveExperiment">保存草稿</el-button></template></el-dialog>
  </section>
</template>

<style scoped>
.ads-panel{overflow:hidden;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:24px;border-bottom:1px solid var(--color-border);background:linear-gradient(135deg,#f7eee2,#edf3ef)}.panel-head p,.section-title p{margin:0 0 7px;color:var(--color-accent);font-size:10px;font-weight:800;letter-spacing:.17em}.panel-head h2{margin:0;font-family:var(--font-display);font-size:28px;font-weight:500}.panel-head span{display:block;margin-top:7px;color:var(--color-muted);font-size:12px}.head-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}.ads-panel>.el-alert{border-radius:0}.workspace{display:grid;min-height:560px;grid-template-columns:210px minmax(0,1fr);border-bottom:1px solid var(--color-border)}.history{padding:14px;border-right:1px solid var(--color-border);background:#f8f6f1}.aside-title{display:flex;justify-content:space-between;padding:6px}.aside-title span{color:var(--color-muted);font-size:10px}.history button{display:flex;width:100%;flex-direction:column;gap:5px;margin-top:7px;padding:11px;border:1px solid transparent;border-radius:8px;background:transparent;text-align:left;cursor:pointer}.history button.active,.history button:hover{border-color:#d9cfc1;background:white}.history button span{display:flex;align-items:center;justify-content:space-between}.history button small{color:var(--color-muted);font-size:10px}.recommendation{padding:22px}.result-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.result-head h3{margin:0;font-family:var(--font-display);font-size:24px;font-weight:500}.result-head span{display:block;margin-top:5px;color:var(--color-muted);font-size:10px}.recommendation>.el-alert{margin-top:14px}.section-grid{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-top:15px}.section-grid article{padding:15px;border:1px solid var(--color-border);border-radius:9px;background:#fffefa}.section-grid small{color:var(--color-accent);font-weight:700}.section-grid p{margin:9px 0 0;line-height:1.65;white-space:pre-wrap}.confirmation{display:flex;justify-content:space-between;margin-top:14px;padding:12px;border-radius:8px;background:#edf3ed}.confirmation span{color:var(--color-muted);font-size:11px}.experiments{padding:22px;background:#f8f7f2}.section-title{display:flex;align-items:flex-end;justify-content:space-between}.section-title h3{margin:0;font-family:var(--font-display);font-size:25px;font-weight:500}.section-title>span{color:var(--color-muted);font-size:11px}.experiment-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:15px}.experiment-grid article{padding:16px;border:1px solid var(--color-border);border-radius:10px;background:#fff}.experiment-grid article>div:first-child{display:flex;align-items:center;justify-content:space-between}.experiment-grid small{color:var(--color-muted);font-size:9px}.experiment-grid h4{margin:12px 0 7px;font-family:var(--font-display);font-size:19px;font-weight:500}.experiment-grid p{min-height:45px;color:var(--color-muted);font-size:11px;line-height:1.6}.experiment-grid dl{display:flex;justify-content:space-between;margin:12px 0}.experiment-grid dl div{display:flex;flex-direction:column}.experiment-grid dt{color:var(--color-muted);font-size:9px}.experiment-grid dd{margin:4px 0 0;font-size:11px}.experiment-grid footer{display:flex;flex-wrap:wrap;padding-top:8px;border-top:1px dashed var(--color-border)}.dialog-form{margin-top:18px}.dialog-form :deep(.el-select){width:100%}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 14px}@media(max-width:1000px){.experiment-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:800px){.panel-head,.result-head,.section-title{align-items:flex-start;flex-direction:column}.workspace{grid-template-columns:1fr}.history{display:flex;overflow-x:auto;border-right:0;border-bottom:1px solid var(--color-border)}.history button{min-width:155px}.section-grid,.experiment-grid{grid-template-columns:1fr}}@media(max-width:600px){.form-grid{grid-template-columns:1fr}.recommendation,.experiments{padding:14px}}
</style>
