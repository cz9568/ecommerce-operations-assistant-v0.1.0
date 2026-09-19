<script setup lang="ts">
import { Download, Refresh, UploadFilled, View } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import type { UploadFile, UploadFiles } from "element-plus"
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { confirmImport, downloadImportErrors, downloadImportTemplate, getImportBatch, getImportBatches, initializeDemoData, uploadImport } from "../api/imports"
import { getApiErrorMessage } from "../api/http"
import PageHeader from "../components/common/PageHeader.vue"
import { useAuthStore } from "../stores/auth"
import type { ImportBatch, ImportPreview, ImportType } from "../types/domain"
import { formatDate } from "../utils/domain"

const labels: Record<ImportType, string> = { products: "商品", sku_inventory: "SKU 与库存", performance_records: "经营数据" }
const route = useRoute(); const router = useRouter(); const authStore = useAuthStore()
const initialType = String(route.query.type || "products") as ImportType
const importType = ref<ImportType>(Object.hasOwn(labels, initialType) ? initialType : "products")
const selectedFile = ref<File | null>(null); const uploadFiles = ref<UploadFiles>([])
const preview = ref<ImportPreview | null>(null); const batches = ref<ImportBatch[]>([])
const loading = ref(false); const processing = ref(false)
const canDemo = computed(() => authStore.can("settings.manage"))
const readyToConfirm = computed(() => preview.value?.batch.batch_status === "validated" && Boolean(preview.value.batch.valid_rows))
const rawColumns = computed(() => preview.value?.rows.length ? Object.keys(preview.value.rows[0]?.raw_data || {}) : [])

async function loadBatches(): Promise<void> {
  loading.value = true
  try { batches.value = (await getImportBatches()).items }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "导入历史加载失败")) }
  finally { loading.value = false }
}
function fileChanged(file: UploadFile, files: UploadFiles): void {
  selectedFile.value = file.raw || null; uploadFiles.value = files.slice(-1); preview.value = null
}
function fileRemoved(): void { selectedFile.value = null; uploadFiles.value = []; preview.value = null }
async function downloadTemplate(): Promise<void> {
  try { await downloadImportTemplate(importType.value) }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "模板下载失败")) }
}
async function validateFile(): Promise<void> {
  if (!selectedFile.value) { ElMessage.warning("请先选择 CSV 文件"); return }
  processing.value = true
  try { preview.value = await uploadImport(importType.value, selectedFile.value); await loadBatches(); ElMessage.success("文件解析完成，请核对影响范围") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "文件解析失败")) }
  finally { processing.value = false }
}
async function confirmBatch(): Promise<void> {
  if (!preview.value) return
  await ElMessageBox.confirm(`将写入 ${preview.value.batch.valid_rows} 行有效数据；无效行不会写入。`, "确认导入", { type: "warning", confirmButtonText: "确认写入" })
  processing.value = true
  try { preview.value = await confirmImport(preview.value.batch.id); await loadBatches(); ElMessage.success(`导入完成：成功 ${preview.value.batch.success_rows} 行，失败 ${preview.value.batch.failed_rows} 行`) }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "确认导入失败")) }
  finally { processing.value = false }
}
async function openBatch(item: ImportBatch): Promise<void> {
  try { preview.value = await getImportBatch(item.id); importType.value = item.import_type }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "批次详情加载失败")) }
}
function openBatchRow(item: unknown): void { void openBatch(item as ImportBatch) }
async function downloadErrors(): Promise<void> { if (preview.value) await downloadImportErrors(preview.value.batch.id) }
async function createDemo(): Promise<void> {
  await ElMessageBox.confirm("将创建带【演示】标识的完整闭环样例；重复执行不会复制数据。", "初始化演示数据", { type: "warning", confirmButtonText: "创建演示数据" })
  processing.value = true
  try { const result = await initializeDemoData(); ElMessage.success(result.message); await router.push({ name: "product-detail", params: { productId: result.product_id, tab: "overview" } }) }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "演示数据初始化失败")) }
  finally { processing.value = false }
}
watch(importType, () => { selectedFile.value = null; uploadFiles.value = []; preview.value = null })
onMounted(() => void loadBatches())
</script>

<template>
  <section class="import-center">
    <PageHeader eyebrow="IMPORT CENTER" title="数据导入中心" description="下载标准模板，上传后先逐行校验预览；只有人工确认才会写入业务数据。">
      <template #actions><el-button :icon="Refresh" :loading="loading" @click="loadBatches">刷新</el-button><el-button v-if="canDemo" type="primary" plain :loading="processing" @click="createDemo">初始化演示数据</el-button></template>
    </PageHeader>
    <div class="workflow">
      <article class="upload-card">
        <div class="step-title"><span>01</span><div><h3>选择类型与文件</h3><p>仅支持 UTF-8 CSV，最大 2MB、1000 行。</p></div></div>
        <el-segmented v-model="importType" :options="Object.entries(labels).map(([value, label]) => ({ value, label }))" />
        <el-button class="template" :icon="Download" @click="downloadTemplate">下载{{ labels[importType] }}模板</el-button>
        <el-upload drag accept=".csv,text/csv" :auto-upload="false" :limit="1" :file-list="uploadFiles" :on-change="fileChanged" :on-remove="fileRemoved"><el-icon class="el-icon--upload"><UploadFilled /></el-icon><div class="el-upload__text">拖入 CSV，或<em>点击选择</em></div></el-upload>
        <el-button type="primary" :loading="processing" :disabled="!selectedFile" @click="validateFile">解析并校验</el-button>
      </article>
      <article class="notes-card"><div class="step-title"><span>02</span><div><h3>字段与策略</h3><p>模板示例行仅作格式说明，请替换为真实 ID。</p></div></div><template v-if="preview"><dl><template v-for="(value, key) in preview.field_notes" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></template></dl></template><el-empty v-else description="上传后显示该类型的字段说明" :image-size="60" /></article>
    </div>
    <section v-if="preview" class="preview-card">
      <header><div><p>03 · 预览与确认</p><h2>批次 #{{ preview.batch.id }} · {{ preview.batch.original_filename }}</h2></div><div class="stats"><span>总行数 <b>{{ preview.batch.total_rows }}</b></span><span class="ok">有效 <b>{{ preview.batch.valid_rows }}</b></span><span class="bad">失败 <b>{{ preview.batch.failed_rows }}</b></span></div></header>
      <el-alert v-if="preview.batch.batch_status === 'validated'" title="当前仅保存校验预览，尚未写入商品、库存或经营数据。" type="info" show-icon :closable="false" />
      <div class="preview-table"><el-table :data="preview.rows" max-height="430"><el-table-column prop="row_number" label="行" width="62" fixed /><el-table-column label="状态" width="90" fixed><template #default="{ row }"><el-tag :type="['valid','imported'].includes(row.row_status) ? 'success' : 'danger'">{{ row.row_status }}</el-tag></template></el-table-column><el-table-column v-for="column in rawColumns" :key="column" :prop="`raw_data.${column}`" :label="column" min-width="130" show-overflow-tooltip /><el-table-column label="错误" min-width="260" fixed="right"><template #default="{ row }"><span class="error-text">{{ row.errors.map((item: { message: string }) => item.message).join('；') || '—' }}</span></template></el-table-column></el-table></div>
      <footer><el-button v-if="preview.batch.failed_rows" :icon="Download" @click="downloadErrors">下载错误行</el-button><el-button v-if="preview.batch.batch_status === 'validated'" type="primary" :loading="processing" :disabled="!readyToConfirm" @click="confirmBatch">确认导入 {{ preview.batch.valid_rows }} 行</el-button><el-tag v-else type="success" size="large">已完成：成功 {{ preview.batch.success_rows }} / 失败 {{ preview.batch.failed_rows }}</el-tag></footer>
    </section>
    <section class="history-card"><header><div><p>IMPORT HISTORY</p><h2>导入批次</h2></div></header><el-table v-loading="loading" :data="batches" empty-text="暂无导入记录"><el-table-column prop="id" label="批次" width="80" /><el-table-column label="类型"><template #default="{ row }">{{ labels[row.import_type as ImportType] }}</template></el-table-column><el-table-column prop="original_filename" label="文件" min-width="180" /><el-table-column label="结果"><template #default="{ row }">{{ row.success_rows }} 成功 / {{ row.failed_rows }} 失败 / {{ row.total_rows }} 总计</template></el-table-column><el-table-column label="状态"><template #default="{ row }"><el-tag>{{ row.batch_status }}</el-tag></template></el-table-column><el-table-column label="创建时间" min-width="150"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column><el-table-column width="90"><template #default="{ row }"><el-button text :icon="View" @click="openBatchRow(row)">查看</el-button></template></el-table-column></el-table></section>
  </section>
</template>

<style scoped>
.import-center{display:flex;flex-direction:column;gap:18px}.workflow{display:grid;grid-template-columns:1fr 1fr;gap:16px}.upload-card,.notes-card,.preview-card,.history-card{padding:22px;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.upload-card{display:flex;flex-direction:column;gap:16px}.step-title{display:flex;gap:12px}.step-title>span{display:grid;width:34px;height:34px;place-items:center;border-radius:50%;background:#17221e;color:#fff;font-size:11px}.step-title h3{margin:0;font-family:var(--font-display);font-size:21px;font-weight:500}.step-title p{margin:4px 0 0;color:var(--color-muted);font-size:11px}.template{align-self:flex-start}.notes-card dl{display:grid;grid-template-columns:150px 1fr;gap:0;margin:16px 0 0}.notes-card dt,.notes-card dd{margin:0;padding:10px;border-bottom:1px solid var(--color-border);font-size:12px}.notes-card dt{font-weight:700}.notes-card dd{color:var(--color-muted)}.preview-card header,.history-card header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px}.preview-card header p,.history-card header p{margin:0;color:var(--color-accent);font-size:10px;font-weight:800;letter-spacing:.14em}.preview-card h2,.history-card h2{margin:5px 0 0;font-family:var(--font-display);font-size:24px;font-weight:500}.stats{display:flex;gap:7px}.stats span{padding:8px 11px;border-radius:7px;background:#f0f0eb;color:var(--color-muted);font-size:11px}.stats .ok{background:#edf5ee;color:#3b7048}.stats .bad{background:#f9ece9;color:#a24d40}.preview-table{margin-top:14px}.preview-card footer{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}.error-text{color:#a24d40;font-size:11px}@media(max-width:800px){.workflow{grid-template-columns:1fr}.preview-card header{flex-direction:column;gap:12px}.notes-card dl{grid-template-columns:1fr}}
</style>
