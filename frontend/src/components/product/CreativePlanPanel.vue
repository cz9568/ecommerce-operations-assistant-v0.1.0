<script setup lang="ts">
import { Clock, Delete, EditPen, MagicStick, Refresh, Select } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"

import {
  generateCreativePlans,
  getCreativePlanRevisions,
  getCreativePlans,
  updateCreativePlan,
  updateCreativePlanStatus,
} from "../../api/creativePlans"
import { getApiErrorMessage } from "../../api/http"
import { createGenerationJob } from "../../api/generationJobs"
import { useAuthStore } from "../../stores/auth"
import type {
  CreativePlan,
  CreativePlanRevision,
  CreativePlanStatus,
  CreativePlanType,
  MainImagePlanContent,
  VideoScriptContent,
} from "../../types/domain"
import { formatDate } from "../../utils/domain"

const props = defineProps<{ productId: number; planType: CreativePlanType }>()
const emit = defineEmits<{ dirty: [value: boolean] }>()
const authStore = useAuthStore()
const router = useRouter()
const records = ref<CreativePlan[]>([])
const total = ref(0)
const page = ref(1)
const statusFilter = ref<CreativePlanStatus | "">("")
const loading = ref(false)
const generating = ref(false)
const saving = ref(false)
const loadError = ref("")
const generateDialog = ref(false)
const editDialog = ref(false)
const revisionDrawer = ref(false)
const notes = ref("")
const editing = ref<CreativePlan | null>(null)
const revisionPlan = ref<CreativePlan | null>(null)
const revisions = ref<CreativePlanRevision[]>([])
const revisionsLoading = ref(false)
const creatingJobId = ref<number | null>(null)
const pendingIdempotencyKeys = new Map<string, string>()
const isImage = computed(() => props.planType === "main_image")
const canGenerate = computed(() => authStore.can("ai.generate"))
const canWrite = computed(() => authStore.can("product.write"))
const title = computed(() => (isImage.value ? "主图创意方案" : "短视频脚本"))
const description = computed(() => isImage.value
  ? "每批生成至少三个完整方向，选中一个方案后可在 M6 发起图片生成。"
  : "每批生成至少三条脚本，完整保存钩子、分镜、口播与转化引导。")
const statusLabels: Record<CreativePlanStatus, string> = { draft: "草稿", selected: "已选中", archived: "已归档" }
const mainEdit = reactive<MainImagePlanContent>({ title: "", visual_concept: "", composition: "", copy_text: "", generation_prompt: "", rationale: "" })
const videoEdit = reactive<VideoScriptContent>({ title: "", hook: "", scenes: [], call_to_action: "", rationale: "" })

watch([generateDialog, editDialog], ([generateOpen, editOpen]) => emit("dirty", generateOpen || editOpen))

function imageContent(plan: CreativePlan): MainImagePlanContent {
  return plan.content as MainImagePlanContent
}
function videoContent(plan: CreativePlan): VideoScriptContent {
  return plan.content as VideoScriptContent
}
function statusType(status: CreativePlanStatus): "success" | "warning" | "info" {
  return status === "selected" ? "success" : status === "archived" ? "info" : "warning"
}

async function loadRecords(): Promise<void> {
  loading.value = true
  loadError.value = ""
  try {
    const result = await getCreativePlans(props.productId, {
      plan_type: props.planType,
      plan_status: statusFilter.value || undefined,
      page: page.value,
      page_size: 20,
    })
    records.value = result.items
    total.value = result.total
  } catch (error) {
    loadError.value = getApiErrorMessage(error, `${title.value}加载失败`)
  } finally {
    loading.value = false
  }
}

function openGenerate(): void {
  notes.value = ""
  generateDialog.value = true
}
async function confirmGenerate(): Promise<void> {
  generating.value = true
  try {
    const created = await generateCreativePlans(props.productId, {
      plan_type: props.planType,
      notes: notes.value.trim() || undefined,
    })
    generateDialog.value = false
    statusFilter.value = ""
    page.value = 1
    await loadRecords()
    ElMessage.success(`已生成 ${created.length} 个${isImage.value ? "主图方向" : "视频脚本"}`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "生成失败，未创建方案记录"))
  } finally {
    generating.value = false
  }
}

function openEdit(plan: CreativePlan): void {
  editing.value = plan
  if (isImage.value) Object.assign(mainEdit, structuredClone(imageContent(plan)))
  else Object.assign(videoEdit, structuredClone(videoContent(plan)))
  editDialog.value = true
}
function addScene(): void {
  videoEdit.scenes.push({ order: videoEdit.scenes.length + 1, visual: "", voiceover: "", duration_seconds: 5 })
}
function removeScene(index: number): void {
  videoEdit.scenes.splice(index, 1)
  videoEdit.scenes.forEach((scene, sceneIndex) => { scene.order = sceneIndex + 1 })
}
async function saveEdit(): Promise<void> {
  if (!editing.value) return
  const content = isImage.value
    ? structuredClone(mainEdit)
    : { ...structuredClone(videoEdit), scenes: videoEdit.scenes.map((scene, index) => ({ ...scene, order: index + 1 })) }
  saving.value = true
  try {
    const updated = await updateCreativePlan(props.productId, editing.value.id, {
      content,
      expected_version: editing.value.version_no,
    })
    records.value = records.value.map((item) => item.id === updated.id ? updated : item)
    editDialog.value = false
    ElMessage.success("方案修改已保存并形成新版本")
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "保存失败，请刷新后重试"))
  } finally {
    saving.value = false
  }
}

async function changeStatus(plan: CreativePlan, status: CreativePlanStatus): Promise<void> {
  const action = status === "selected" ? "选中" : status === "archived" ? "归档" : "取消选中"
  try {
    await ElMessageBox.confirm(
      status === "selected" ? "选中后，同类型原有选中方案会自动回到草稿。" : `确认${action}“${plan.title}”吗？`,
      `${action}${isImage.value ? "主图方案" : "视频脚本"}`,
      { type: status === "archived" ? "warning" : "info", confirmButtonText: `确认${action}` },
    )
    await updateCreativePlanStatus(props.productId, plan.id, { status, expected_version: plan.version_no })
    await loadRecords()
    ElMessage.success(`已${action}`)
  } catch (error) {
    if (error === "cancel" || error === "close") return
    ElMessage.error(getApiErrorMessage(error, `${action}失败`))
  }
}

async function openRevisions(plan: CreativePlan): Promise<void> {
  revisionPlan.value = plan
  revisionDrawer.value = true
  revisionsLoading.value = true
  try { revisions.value = await getCreativePlanRevisions(props.productId, plan.id) }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "版本历史加载失败")) }
  finally { revisionsLoading.value = false }
}

async function createMediaTask(plan: CreativePlan): Promise<void> {
  if (plan.status !== "selected") return
  const kindLabel = isImage.value ? "图片" : "视频"
  try {
    await ElMessageBox.confirm(
      `将锁定方案 #${plan.id} 的 v${plan.version_no} 内容并创建异步${kindLabel}任务。创建后由 Worker 在后台执行。`,
      `确认生成${kindLabel}`,
      { type: "info", confirmButtonText: "创建任务" },
    )
  } catch { return }
  const requestKey = `${plan.id}:${plan.version_no}`
  const idempotencyKey = pendingIdempotencyKeys.get(requestKey) || crypto.randomUUID()
  pendingIdempotencyKeys.set(requestKey, idempotencyKey)
  creatingJobId.value = plan.id
  try {
    const job = await createGenerationJob(props.productId, {
      creative_plan_id: plan.id,
      creative_plan_version_no: plan.version_no,
      idempotency_key: idempotencyKey,
      size: isImage.value ? "1024x1024" : "1280*720",
      duration_seconds: isImage.value ? undefined : 5,
    })
    pendingIdempotencyKeys.delete(requestKey)
    ElMessage.success(`${kindLabel}任务 #${job.id} 已创建，Worker 将在后台处理`)
    await router.push({
      name: "product-detail",
      params: { productId: props.productId, tab: "tasks" },
      query: { job: String(job.id) },
    })
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, `${kindLabel}任务创建失败`))
  } finally {
    creatingJobId.value = null
  }
}

onMounted(() => void loadRecords())
watch(() => [props.productId, props.planType] as const, () => { page.value = 1; statusFilter.value = ""; void loadRecords() })
</script>

<template>
  <section class="creative-panel">
    <header class="panel-head">
      <div><p>{{ isImage ? 'MAIN IMAGE DIRECTIONS' : 'VIDEO SCRIPTS' }}</p><h2>{{ title }}</h2><span>{{ description }}</span></div>
      <div class="head-actions"><el-select v-model="statusFilter" clearable placeholder="全部状态" @change="page = 1; loadRecords()"><el-option v-for="(label, key) in statusLabels" :key="key" :label="label" :value="key" /></el-select><el-button :icon="Refresh" :loading="loading" @click="loadRecords">刷新</el-button><el-button v-if="canGenerate" type="primary" :icon="MagicStick" @click="openGenerate">AI 生成{{ isImage ? '方向' : '脚本' }}</el-button></div>
    </header>
    <el-alert v-if="loadError" :title="loadError" type="error" show-icon :closable="false"><template #default><el-button link type="primary" @click="loadRecords">重新加载</el-button></template></el-alert>
    <div v-loading="loading" class="plan-grid">
      <article v-for="plan in records" :key="plan.id" class="plan-card" :class="[`status-${plan.status}`]">
        <div class="card-head"><div><span>#{{ plan.id }} · v{{ plan.version_no }}</span><h3>{{ plan.title }}</h3></div><el-tag :type="statusType(plan.status)" effect="plain">{{ statusLabels[plan.status] }}</el-tag></div>
        <template v-if="isImage">
          <div class="feature"><small>视觉概念</small><p>{{ imageContent(plan).visual_concept }}</p></div>
          <div class="feature"><small>画面构图</small><p>{{ imageContent(plan).composition }}</p></div>
          <div class="copy-line">{{ imageContent(plan).copy_text }}</div>
          <details><summary>查看生图提示词</summary><p>{{ imageContent(plan).generation_prompt }}</p></details>
        </template>
        <template v-else>
          <div class="hook">“{{ videoContent(plan).hook }}”</div>
          <div class="scenes"><div v-for="scene in videoContent(plan).scenes" :key="scene.order"><b>{{ scene.order }}</b><span><strong>{{ scene.visual }}</strong><small>{{ scene.voiceover }} · {{ scene.duration_seconds }} 秒</small></span></div></div>
          <div class="cta">转化引导：{{ videoContent(plan).call_to_action }}</div>
        </template>
        <p class="rationale">{{ plan.rationale }}</p>
        <div class="metadata"><span>{{ plan.model_name }}</span><span>{{ plan.prompt_version }}</span><span>{{ formatDate(plan.created_at) }}</span></div>
        <div class="card-actions"><el-button :icon="Clock" @click="openRevisions(plan)">版本</el-button><template v-if="canWrite && plan.status !== 'archived'"><el-button :icon="EditPen" @click="openEdit(plan)">编辑</el-button><el-button v-if="plan.status === 'draft'" type="primary" plain :icon="Select" @click="changeStatus(plan, 'selected')">选中</el-button><el-button v-else-if="plan.status === 'selected'" @click="changeStatus(plan, 'draft')">取消选中</el-button><el-button v-if="plan.status === 'draft'" type="danger" plain :icon="Delete" @click="changeStatus(plan, 'archived')">归档</el-button></template></div>
        <el-tooltip v-if="canGenerate && plan.status === 'selected'" content="创建任务后立即返回，媒体由独立 Worker 异步生成" placement="top"><el-button class="generation-ready" type="primary" :loading="creatingJobId === plan.id" @click="createMediaTask(plan)">生成{{ isImage ? '图片' : '视频' }}</el-button></el-tooltip>
      </article>
      <el-empty v-if="!records.length && !loading" :description="`尚无${title}`"><el-button v-if="canGenerate" type="primary" :icon="MagicStick" @click="openGenerate">生成第一批</el-button></el-empty>
    </div>
    <el-pagination v-if="total > 20" class="pager" background layout="prev,pager,next" :current-page="page" :page-size="20" :total="total" @update:current-page="(value:number) => { page = value; loadRecords() }" />

    <el-dialog v-model="generateDialog" :title="`确认生成${title}`" width="min(580px, 94vw)" :close-on-click-modal="!generating">
      <el-alert title="系统会引用该商品最新诊断及其商品、竞品、SKU/库存快照；仅在完整结构校验通过后创建方案。" type="info" show-icon :closable="false" />
      <el-form label-position="top" class="dialog-form"><el-form-item label="本批补充要求（选填）"><el-input v-model="notes" type="textarea" :rows="4" maxlength="2000" show-word-limit :placeholder="isImage ? '例如：需要适合天猫首图的简洁场景' : '例如：控制在 30 秒，前 3 秒突出痛点'" /></el-form-item></el-form>
      <template #footer><el-button :disabled="generating" @click="generateDialog = false">取消</el-button><el-button type="primary" :loading="generating" @click="confirmGenerate">确认并生成</el-button></template>
    </el-dialog>

    <el-dialog v-model="editDialog" :title="`编辑${isImage ? '主图方案' : '视频脚本'}`" width="min(840px, 95vw)" :close-on-click-modal="!saving">
      <el-alert title="保存将产生新的不可变版本记录；归档方案不可编辑。" type="warning" :closable="false" />
      <el-form v-if="isImage" :model="mainEdit" label-position="top" class="edit-form"><el-form-item label="方向标题" required><el-input v-model="mainEdit.title" maxlength="200" /></el-form-item><el-form-item label="视觉概念" required><el-input v-model="mainEdit.visual_concept" type="textarea" :rows="3" /></el-form-item><el-form-item label="画面构图" required><el-input v-model="mainEdit.composition" type="textarea" :rows="3" /></el-form-item><el-form-item label="画面文案" required><el-input v-model="mainEdit.copy_text" type="textarea" :rows="2" /></el-form-item><el-form-item label="生图提示词" required><el-input v-model="mainEdit.generation_prompt" type="textarea" :rows="4" /></el-form-item><el-form-item label="方案理由" required><el-input v-model="mainEdit.rationale" type="textarea" :rows="3" /></el-form-item></el-form>
      <el-form v-else :model="videoEdit" label-position="top" class="edit-form"><el-form-item label="脚本标题" required><el-input v-model="videoEdit.title" maxlength="200" /></el-form-item><el-form-item label="开场钩子" required><el-input v-model="videoEdit.hook" type="textarea" :rows="2" /></el-form-item><div class="scene-editor"><div class="scene-title"><strong>分镜</strong><el-button size="small" @click="addScene">新增分镜</el-button></div><div v-for="(scene, index) in videoEdit.scenes" :key="index" class="scene-row"><span>{{ index + 1 }}</span><el-input v-model="scene.visual" type="textarea" :rows="2" placeholder="画面" /><el-input v-model="scene.voiceover" type="textarea" :rows="2" placeholder="口播" /><el-input-number v-model="scene.duration_seconds" :min="1" :max="120" /><el-button link type="danger" :disabled="videoEdit.scenes.length === 1" @click="removeScene(index)">删除</el-button></div></div><el-form-item label="转化引导" required><el-input v-model="videoEdit.call_to_action" type="textarea" :rows="2" /></el-form-item><el-form-item label="脚本理由" required><el-input v-model="videoEdit.rationale" type="textarea" :rows="3" /></el-form-item></el-form>
      <template #footer><el-button :disabled="saving" @click="editDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveEdit">保存新版本</el-button></template>
    </el-dialog>

    <el-drawer v-model="revisionDrawer" :title="`版本历史 · ${revisionPlan?.title || ''}`" size="min(680px, 94vw)"><div v-loading="revisionsLoading" class="revision-list"><article v-for="revision in revisions" :key="revision.id"><div><strong>v{{ revision.version_no }}</strong><el-tag size="small" :type="statusType(revision.status)" effect="plain">{{ statusLabels[revision.status] }}</el-tag><span>{{ formatDate(revision.created_at) }}</span></div><h4>{{ revision.title }}</h4><p>{{ revision.rationale }}</p></article><el-empty v-if="!revisions.length && !revisionsLoading" description="尚无版本记录" /></div></el-drawer>
  </section>
</template>

<style scoped>
.creative-panel{overflow:hidden;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:24px;border-bottom:1px solid var(--color-border);background:linear-gradient(135deg,#faf6ee,#eef3ef)}.panel-head p{margin:0 0 7px;color:var(--color-accent);font-size:10px;font-weight:800;letter-spacing:.17em}.panel-head h2{margin:0;font-family:var(--font-display);font-size:28px;font-weight:500}.panel-head span{display:block;margin-top:7px;color:var(--color-muted);font-size:12px}.head-actions{display:flex;gap:8px}.head-actions :deep(.el-select){width:125px}.plan-grid{display:grid;min-height:420px;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;padding:20px}.plan-card{position:relative;display:flex;min-width:0;flex-direction:column;padding:18px;border:1px solid var(--color-border);border-radius:12px;background:#fffefa}.plan-card.status-selected{border-color:#7b9b89;box-shadow:0 8px 25px rgb(66 97 80 / 13%)}.plan-card.status-archived{opacity:.67;background:#f4f3ef}.card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.card-head span{color:var(--color-muted);font-size:10px}.card-head h3{margin:6px 0 14px;font-family:var(--font-display);font-size:21px;font-weight:500}.feature small{color:var(--color-muted);font-size:10px}.feature p,.plan-card details p{margin:5px 0 12px;line-height:1.6}.copy-line,.hook,.cta{margin:3px 0 12px;padding:10px;border-radius:8px;background:#f3f0e8;color:#7d4d37;font-size:12px;line-height:1.55}.hook{font-family:var(--font-display);font-size:16px}.cta{background:#edf2ed;color:#42614f}.plan-card details{margin-bottom:10px;color:var(--color-muted);font-size:11px}.plan-card details summary{cursor:pointer}.scenes{display:flex;flex-direction:column;gap:7px;margin-bottom:10px}.scenes>div{display:flex;gap:8px;align-items:flex-start}.scenes b{display:grid;width:22px;height:22px;flex:0 0 auto;place-items:center;border-radius:50%;background:#17221e;color:white;font-size:10px}.scenes span{display:flex;min-width:0;flex-direction:column}.scenes strong{font-size:12px}.scenes small{margin-top:3px;color:var(--color-muted);line-height:1.45}.rationale{margin-top:auto;padding-top:10px;border-top:1px dashed var(--color-border);color:var(--color-muted);font-size:11px;line-height:1.6}.metadata{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0;color:var(--color-muted);font-size:9px}.card-actions{display:flex;flex-wrap:wrap;gap:6px}.generation-ready{width:100%;margin-top:9px}.pager{display:flex;justify-content:flex-end;padding:0 20px 20px}.dialog-form,.edit-form{margin-top:18px}.edit-form{max-height:62vh;overflow-y:auto;padding-right:8px}.scene-editor{margin-bottom:18px}.scene-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.scene-row{display:grid;grid-template-columns:28px 1fr 1fr 120px 42px;gap:8px;align-items:center;margin-bottom:9px;padding:10px;border-radius:9px;background:#f5f4ef}.scene-row>span{font-family:var(--font-display);font-size:20px}.revision-list{display:flex;flex-direction:column;gap:10px}.revision-list article{padding:14px;border:1px solid var(--color-border);border-radius:9px}.revision-list article>div{display:flex;align-items:center;gap:8px}.revision-list article span{margin-left:auto;color:var(--color-muted);font-size:10px}.revision-list h4{margin:10px 0 5px}.revision-list p{margin:0;color:var(--color-muted);line-height:1.6}@media(max-width:1100px){.plan-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){.panel-head{flex-direction:column}.head-actions{width:100%;flex-wrap:wrap}.plan-grid{grid-template-columns:1fr}.scene-row{grid-template-columns:24px 1fr}.scene-row :deep(.el-input-number){width:100%}}@media(max-width:520px){.plan-grid{padding:12px}.head-actions :deep(.el-select){width:100%}}
</style>
