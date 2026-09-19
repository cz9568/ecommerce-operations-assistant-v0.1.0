<script setup lang="ts">
import { EditPen, MagicStick, Refresh } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"

import { generateDiagnosis, getDiagnoses, updateDiagnosis } from "../../api/diagnoses"
import type { DiagnosisContentField, DiagnosisUpdatePayload } from "../../api/diagnoses"
import { getApiErrorMessage } from "../../api/http"
import { useAuthStore } from "../../stores/auth"
import type { ProductDiagnosis } from "../../types/domain"
import { formatDate } from "../../utils/domain"

const props = defineProps<{ productId: number }>()
const emit = defineEmits<{ dirty: [value: boolean] }>()
const authStore = useAuthStore()
const router = useRouter()
const records = ref<ProductDiagnosis[]>([])
const current = ref<ProductDiagnosis | null>(null)
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const generating = ref(false)
const saving = ref(false)
const loadError = ref("")
const generateDialog = ref(false)
const editDialog = ref(false)
const notes = ref("")
const canGenerate = computed(() => authStore.can("ai.generate"))
const canEdit = computed(() => authStore.can("product.write"))

const sections: Array<{ field: DiagnosisContentField; label: string; hint: string }> = [
  { field: "positioning", label: "商品定位", hint: "市场角色与差异化方向" },
  { field: "price_band", label: "价格带判断", hint: "价格位置与价值表达" },
  { field: "audience_insights", label: "人群洞察", hint: "目标人群与决策关注点" },
  { field: "pain_points", label: "核心痛点", hint: "用户问题与购买阻力" },
  { field: "selling_point_analysis", label: "卖点分析", hint: "优势、证据与表达次序" },
  { field: "risks", label: "风险提示", hint: "数据边界与经营风险" },
  { field: "recommendations", label: "行动建议", hint: "可执行的下一步动作" },
]
const editForm = reactive<Record<DiagnosisContentField, string>>({
  positioning: "",
  price_band: "",
  audience_insights: "",
  pain_points: "",
  selling_point_analysis: "",
  risks: "",
  recommendations: "",
})
const sourceSummary = computed(() => {
  const snapshot = current.value?.input_snapshot
  return {
    competitors: snapshot?.competitors?.length ?? 0,
    skus: snapshot?.sku_inventory?.length ?? 0,
    hasReview: Boolean(snapshot?.source_review),
  }
})
const missingWarnings = computed(() => {
  if (!current.value) return []
  const snapshot = current.value.input_snapshot
  const product = snapshot.product || {}
  const result: string[] = []
  if (!product.target_audience) result.push("目标人群")
  if (!product.selling_points) result.push("商品卖点")
  if (!snapshot.competitors?.length) result.push("竞品数据")
  if (!snapshot.sku_inventory?.length) result.push("SKU 与库存")
  return result
})

watch([generateDialog, editDialog], ([generateOpen, editOpen]) => emit("dirty", generateOpen || editOpen))

async function loadRecords(selectNewest = true): Promise<void> {
  loading.value = true
  loadError.value = ""
  try {
    const result = await getDiagnoses(props.productId, { page: page.value, page_size: 20 })
    records.value = result.items
    total.value = result.total
    if (selectNewest || !current.value || !records.value.some((item) => item.id === current.value?.id)) {
      current.value = records.value[0] || null
    }
  } catch (error) {
    loadError.value = getApiErrorMessage(error, "诊断历史加载失败")
  } finally {
    loading.value = false
  }
}

function openGenerate(): void {
  notes.value = ""
  generateDialog.value = true
}

async function goToSourceReview(): Promise<void> {
  if (!current.value?.source_review_report_id) return
  await router.push({
    name: "product-detail",
    params: { productId: props.productId, tab: "reviews" },
    query: { review: String(current.value.source_review_report_id) },
  })
}

async function confirmGenerate(): Promise<void> {
  generating.value = true
  try {
    const created = await generateDiagnosis(props.productId, { notes: notes.value.trim() || undefined })
    generateDialog.value = false
    page.value = 1
    await loadRecords()
    current.value = records.value.find((item) => item.id === created.id) || created
    ElMessage.success("新诊断已生成并保存")
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "诊断生成失败，未创建诊断记录"))
  } finally {
    generating.value = false
  }
}

function openEdit(): void {
  if (!current.value) return
  for (const item of sections) editForm[item.field] = current.value[item.field]
  editDialog.value = true
}

async function saveEdit(): Promise<void> {
  if (!current.value) return
  if (sections.some((item) => !editForm[item.field].trim())) {
    ElMessage.warning("七项诊断内容都不能为空")
    return
  }
  saving.value = true
  try {
    const payload = Object.fromEntries(
      sections.map((item) => [item.field, editForm[item.field].trim()]),
    ) as Record<DiagnosisContentField, string>
    const updated = await updateDiagnosis(props.productId, current.value.id, {
      ...payload,
      expected_version: current.value.version_no,
    } as DiagnosisUpdatePayload)
    current.value = updated
    records.value = records.value.map((item) => (item.id === updated.id ? updated : item))
    editDialog.value = false
    ElMessage.success("诊断内容已保存")
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "诊断保存失败，请刷新后重试"))
  } finally {
    saving.value = false
  }
}

onMounted(() => void loadRecords())
watch(() => props.productId, () => { page.value = 1; current.value = null; void loadRecords() })
</script>

<template>
  <section class="diagnosis-panel">
    <header class="panel-head">
      <div><p>AI PRODUCT DIAGNOSIS</p><h2>商品经营诊断</h2><span>基于商品、竞品和库存快照生成结构化结论；每次生成独立留档。</span></div>
      <div class="head-actions"><el-button :icon="Refresh" :loading="loading" @click="loadRecords(false)">刷新</el-button><el-button v-if="canGenerate" type="primary" :icon="MagicStick" @click="openGenerate">生成新诊断</el-button></div>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" show-icon :closable="false"><template #default><el-button link type="primary" @click="loadRecords()">重新加载</el-button></template></el-alert>
    <div v-else v-loading="loading" class="workspace">
      <aside class="history">
        <div class="history-title"><strong>诊断历史</strong><span>{{ total }} 份</span></div>
        <button v-for="item in records" :key="item.id" type="button" :class="{ active: current?.id === item.id }" @click="current = item">
          <span><b>#{{ item.id }}</b><el-tag size="small" effect="plain">v{{ item.version_no }}</el-tag></span>
          <small>{{ formatDate(item.created_at) }}</small>
          <em>{{ item.provider_name }} · {{ item.model_name }}</em>
        </button>
        <el-empty v-if="!records.length && !loading" description="尚无诊断记录" :image-size="58" />
        <el-pagination v-if="total > 20" small layout="prev,next" :current-page="page" :page-size="20" :total="total" @update:current-page="(value:number) => { page = value; loadRecords() }" />
      </aside>

      <main v-if="current" class="result">
        <div class="result-meta">
          <div><strong>诊断 #{{ current.id }}</strong><span>生成于 {{ formatDate(current.created_at) }}<template v-if="current.edited_at"> · 编辑于 {{ formatDate(current.edited_at) }}</template></span></div>
          <el-button v-if="canEdit" :icon="EditPen" @click="openEdit">编辑诊断</el-button>
        </div>
        <div class="source-strip">
          <span>竞品 <b>{{ sourceSummary.competitors }}</b></span><span>SKU/库存 <b>{{ sourceSummary.skus }}</b></span><el-button v-if="current.source_review_report_id" link type="primary" @click="goToSourceReview">来源复盘 #{{ current.source_review_report_id }}</el-button><span v-else>复盘 <b>未关联</b></span><span>版本 <b>{{ current.prompt_version }}</b></span>
        </div>
        <el-alert v-if="missingWarnings.length" :title="`生成时缺少：${missingWarnings.join('、')}。相关结论应结合后续数据复核。`" type="warning" show-icon :closable="false" />
        <div class="section-grid">
          <article v-for="item in sections" :key="item.field" :class="{ wide: item.field === 'recommendations' }">
            <div><h3>{{ item.label }}</h3><small>{{ item.hint }}</small></div><p>{{ current[item.field] }}</p>
          </article>
        </div>
        <footer>Provider {{ current.provider_name }} · Model {{ current.model_name }} · Schema {{ current.schema_version }} · 内容版本 v{{ current.version_no }}</footer>
      </main>
      <div v-else-if="!loading" class="empty-result"><el-empty description="生成第一份商品诊断后，结构化结论会显示在这里"><el-button v-if="canGenerate" type="primary" :icon="MagicStick" @click="openGenerate">生成诊断</el-button></el-empty></div>
    </div>

    <el-dialog v-model="generateDialog" title="确认生成商品诊断" width="min(560px, 94vw)" :close-on-click-modal="!generating">
      <el-alert title="将读取当前商品、启用竞品、SKU/库存和可选复盘的快照。生成成功后会创建一份新的历史记录。" type="info" show-icon :closable="false" />
      <el-form label-position="top" class="dialog-form"><el-form-item label="补充说明（选填）"><el-input v-model="notes" type="textarea" :rows="4" maxlength="2000" show-word-limit placeholder="例如：重点关注年轻租房人群的价格敏感度" /></el-form-item></el-form>
      <template #footer><el-button :disabled="generating" @click="generateDialog = false">取消</el-button><el-button type="primary" :loading="generating" @click="confirmGenerate">确认并生成</el-button></template>
    </el-dialog>

    <el-dialog v-model="editDialog" title="编辑结构化诊断" width="min(820px, 95vw)" :close-on-click-modal="!saving">
      <el-alert title="保存时会校验内容版本；若他人已修改，请刷新后重新编辑。AI 原始输出和输入快照不会被覆盖。" type="warning" :closable="false" />
      <el-form label-position="top" class="edit-form"><el-form-item v-for="item in sections" :key="item.field" :label="item.label" required><el-input v-model="editForm[item.field]" type="textarea" :rows="3" maxlength="4000" show-word-limit /></el-form-item></el-form>
      <template #footer><el-button :disabled="saving" @click="editDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveEdit">保存修改</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.diagnosis-panel{overflow:hidden;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding:24px;border-bottom:1px solid var(--color-border);background:linear-gradient(135deg,#f9f5ed,#f0f4ef)}.panel-head p{margin:0 0 7px;color:var(--color-accent);font-size:10px;font-weight:800;letter-spacing:.17em}.panel-head h2{margin:0;font-family:var(--font-display);font-size:28px;font-weight:500}.panel-head span{display:block;margin-top:7px;color:var(--color-muted);font-size:12px}.head-actions{display:flex;gap:8px}.workspace{display:grid;min-height:590px;grid-template-columns:220px minmax(0,1fr)}.history{padding:15px;border-right:1px solid var(--color-border);background:#f8f7f2}.history-title{display:flex;align-items:center;justify-content:space-between;padding:5px 4px 12px}.history-title span{color:var(--color-muted);font-size:11px}.history button{display:flex;width:100%;flex-direction:column;gap:5px;margin-bottom:7px;padding:11px;border:1px solid transparent;border-radius:9px;background:transparent;color:var(--color-ink);text-align:left;cursor:pointer}.history button:hover,.history button.active{border-color:#d8cec0;background:white}.history button.active{box-shadow:0 5px 16px rgb(31 43 38 / 7%)}.history button span{display:flex;align-items:center;justify-content:space-between}.history button small,.history button em{overflow:hidden;color:var(--color-muted);font-size:10px;font-style:normal;text-overflow:ellipsis;white-space:nowrap}.result{padding:24px}.result-meta{display:flex;align-items:flex-start;justify-content:space-between;gap:15px}.result-meta>div{display:flex;flex-direction:column}.result-meta strong{font-family:var(--font-display);font-size:23px;font-weight:500}.result-meta span{margin-top:4px;color:var(--color-muted);font-size:11px}.source-strip{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}.source-strip span{padding:7px 10px;border-radius:7px;background:#eef1ec;color:var(--color-muted);font-size:11px}.source-strip b{color:var(--color-ink)}.section-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}.section-grid article{padding:17px;border:1px solid var(--color-border);border-radius:10px;background:#fffefa}.section-grid article.wide{grid-column:1/-1;background:#f4f7f2}.section-grid article>div{display:flex;align-items:baseline;justify-content:space-between;gap:12px}.section-grid h3{margin:0;font-family:var(--font-display);font-size:19px;font-weight:500}.section-grid small{color:var(--color-muted);font-size:10px}.section-grid p{margin:13px 0 0;color:#35413b;line-height:1.75;white-space:pre-wrap}.result footer{margin-top:18px;color:var(--color-muted);font-size:10px;text-align:right}.empty-result{display:grid;place-items:center}.dialog-form{margin-top:20px}.edit-form{display:grid;max-height:60vh;grid-template-columns:1fr 1fr;gap:0 18px;overflow-y:auto;margin-top:18px;padding-right:8px}.edit-form :deep(.el-form-item:last-child){grid-column:1/-1}@media(max-width:850px){.workspace{grid-template-columns:1fr}.history{display:flex;overflow-x:auto;gap:8px;border-right:0;border-bottom:1px solid var(--color-border)}.history-title{min-width:90px;flex-direction:column;align-items:flex-start}.history button{min-width:165px}.section-grid{grid-template-columns:1fr}.section-grid article.wide{grid-column:auto}}@media(max-width:600px){.panel-head,.result-meta{flex-direction:column}.head-actions{width:100%;flex-wrap:wrap}.result{padding:16px}.edit-form{grid-template-columns:1fr}.edit-form :deep(.el-form-item:last-child){grid-column:auto}}
</style>
