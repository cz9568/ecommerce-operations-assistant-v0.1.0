<script setup lang="ts">
import { CopyDocument, DataAnalysis, EditPen, Link, MagicStick, Refresh } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { computed, onMounted, reactive, ref, watch } from "vue"

import { createPromotionLink, getPromotionLinkStatistics, getPromotionLinks, suggestPromotionLinks, updatePromotionLink } from "../../api/marketing"
import { getApiErrorMessage } from "../../api/http"
import { useAuthStore } from "../../stores/auth"
import type { PromotionLink, PromotionLinkStatistics, PromotionLinkSuggestion } from "../../types/domain"
import { formatDate } from "../../utils/domain"

const props = defineProps<{ productId: number }>()
const emit = defineEmits<{ dirty: [value: boolean] }>()
const authStore = useAuthStore()
const records = ref<PromotionLink[]>([])
const loading = ref(false)
const saving = ref(false)
const statusFilter = ref("")
const editorOpen = ref(false)
const suggestionsOpen = ref(false)
const statsOpen = ref(false)
const editing = ref<PromotionLink | null>(null)
const suggestions = ref<PromotionLinkSuggestion[]>([])
const stats = ref<PromotionLinkStatistics | null>(null)
const canWrite = computed(() => authStore.can("product.write"))
const form = reactive({ link_name: "", target_url: "", scene_text: "", utm_source: "", utm_medium: "", utm_campaign: "", utm_content: "" })

watch([editorOpen, suggestionsOpen], ([editor, suggestion]) => emit("dirty", editor || suggestion))

async function loadRecords(): Promise<void> {
  loading.value = true
  try { records.value = (await getPromotionLinks(props.productId, statusFilter.value)).items }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "推广链接加载失败")) }
  finally { loading.value = false }
}
function resetForm(): void { Object.assign(form, { link_name: "", target_url: "", scene_text: "", utm_source: "", utm_medium: "", utm_campaign: "", utm_content: "" }) }
function openCreate(suggestion?: PromotionLinkSuggestion): void {
  editing.value = null; resetForm()
  if (suggestion) Object.assign(form, { link_name: suggestion.link_name, target_url: suggestion.target_url, scene_text: suggestion.scene_text, ...suggestion.utm })
  suggestionsOpen.value = false; editorOpen.value = true
}
function openEdit(link: PromotionLink): void {
  editing.value = link
  Object.assign(form, { link_name: link.link_name, target_url: link.target_url, scene_text: link.scene_text || "", utm_source: link.utm.utm_source || "", utm_medium: link.utm.utm_medium || "", utm_campaign: link.utm.utm_campaign || "", utm_content: link.utm.utm_content || "" })
  editorOpen.value = true
}
function utmPayload(): Record<string, string> {
  return Object.fromEntries(Object.entries({ utm_source: form.utm_source, utm_medium: form.utm_medium, utm_campaign: form.utm_campaign, utm_content: form.utm_content }).filter(([, value]) => value.trim()).map(([key, value]) => [key, value.trim()]))
}
async function save(): Promise<void> {
  if (!form.link_name.trim() || !form.target_url.trim()) { ElMessage.warning("链接名称和目标 URL 不能为空"); return }
  saving.value = true
  try {
    const payload = { link_name: form.link_name.trim(), target_url: form.target_url.trim(), scene_text: form.scene_text.trim() || null, utm: utmPayload() }
    if (editing.value) await updatePromotionLink(props.productId, editing.value.id, { expected_version: editing.value.lock_version, ...payload })
    else await createPromotionLink(props.productId, payload)
    editorOpen.value = false; await loadRecords(); ElMessage.success(editing.value ? "推广链接已更新" : "推广链接已创建")
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "推广链接保存失败")) }
  finally { saving.value = false }
}
async function generateSuggestions(): Promise<void> {
  loading.value = true
  try { suggestions.value = await suggestPromotionLinks(props.productId); suggestionsOpen.value = true }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "链接建议生成失败")) }
  finally { loading.value = false }
}
async function toggleStatus(link: PromotionLink): Promise<void> {
  const next = link.status === "active" ? "inactive" : "active"
  if (next === "inactive") await ElMessageBox.confirm("停用后追踪地址将不再跳转，但历史点击统计会保留。", "停用推广链接", { type: "warning", confirmButtonText: "确认停用" })
  try { await updatePromotionLink(props.productId, link.id, { expected_version: link.lock_version, status: next }); await loadRecords(); ElMessage.success(next === "active" ? "链接已启用" : "链接已停用") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "链接状态更新失败")) }
}
async function showStats(link: PromotionLink): Promise<void> {
  try { stats.value = await getPromotionLinkStatistics(props.productId, link.id); statsOpen.value = true }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "点击统计加载失败")) }
}
async function copyTracking(link: PromotionLink): Promise<void> {
  try { await navigator.clipboard.writeText(`${window.location.origin}${link.redirect_path}`); ElMessage.success("追踪链接已复制") }
  catch { ElMessage.error("复制失败，请手工复制追踪地址") }
}

onMounted(() => void loadRecords())
watch(() => props.productId, () => void loadRecords())
</script>

<template>
  <section class="links-panel">
    <header class="panel-head"><div><p>PROMOTION LINKS</p><h2>推广链接与点击统计</h2><span>创建不可猜测的追踪地址；重复点击和疑似机器人会留痕但不计入有效点击。</span></div><div class="actions"><el-select v-model="statusFilter" clearable placeholder="全部状态" @change="loadRecords"><el-option label="启用" value="active" /><el-option label="停用" value="inactive" /></el-select><el-button :icon="Refresh" :loading="loading" @click="loadRecords">刷新</el-button><el-button v-if="canWrite" :icon="MagicStick" @click="generateSuggestions">生成建议</el-button><el-button v-if="canWrite" type="primary" :icon="Link" @click="openCreate()">新建链接</el-button></div></header>
    <div v-loading="loading" class="link-grid">
      <article v-for="item in records" :key="item.id" class="link-card">
        <div class="card-title"><div><small>#{{ item.id }} · {{ item.scene_text || '未设置场景' }}</small><h3>{{ item.link_name }}</h3></div><el-tag :type="item.status === 'active' ? 'success' : 'info'">{{ item.status === 'active' ? '启用' : '停用' }}</el-tag></div>
        <div class="metric"><strong>{{ item.click_count }}</strong><span>累计有效点击</span></div>
        <code>{{ item.redirect_path }}</code><p>{{ item.target_url }}</p>
        <div class="utm"><span v-for="(value, key) in item.utm" :key="key">{{ key }}={{ value }}</span><em v-if="!Object.keys(item.utm).length">未配置 UTM</em></div>
        <footer><small>创建于 {{ formatDate(item.created_at) }}</small><div><el-button text :icon="CopyDocument" @click="copyTracking(item)">复制</el-button><el-button text :icon="DataAnalysis" @click="showStats(item)">统计</el-button><el-button v-if="canWrite" text :icon="EditPen" @click="openEdit(item)">编辑</el-button><el-button v-if="canWrite" text :type="item.status === 'active' ? 'danger' : 'success'" @click="toggleStatus(item)">{{ item.status === 'active' ? '停用' : '启用' }}</el-button></div></footer>
      </article>
      <el-empty v-if="!records.length && !loading" description="尚无推广链接，可先生成三种场景建议" />
    </div>

    <el-dialog v-model="suggestionsOpen" title="推广链接场景建议" width="min(820px, 95vw)"><el-alert title="建议仅帮助配置追踪参数，不会创建广告计划或产生费用。" type="info" show-icon :closable="false" /><div class="suggestion-grid"><article v-for="item in suggestions" :key="item.link_name"><h3>{{ item.link_name }}</h3><p>{{ item.scene_text }}</p><small>{{ Object.entries(item.utm).map(([key, value]) => `${key}=${value}`).join(' · ') }}</small><el-button type="primary" plain @click="openCreate(item)">采用建议并创建</el-button></article></div></el-dialog>
    <el-dialog v-model="editorOpen" :title="editing ? '编辑推广链接' : '新建推广链接'" width="min(700px, 95vw)" :close-on-click-modal="!saving"><el-form label-position="top" class="form-grid"><el-form-item label="链接名称" required><el-input v-model="form.link_name" maxlength="255" /></el-form-item><el-form-item label="使用场景"><el-input v-model="form.scene_text" maxlength="255" /></el-form-item><el-form-item label="目标 URL" required class="wide"><el-input v-model="form.target_url" maxlength="2048" placeholder="https://..." /></el-form-item><el-form-item label="utm_source"><el-input v-model="form.utm_source" maxlength="200" /></el-form-item><el-form-item label="utm_medium"><el-input v-model="form.utm_medium" maxlength="200" /></el-form-item><el-form-item label="utm_campaign"><el-input v-model="form.utm_campaign" maxlength="200" /></el-form-item><el-form-item label="utm_content"><el-input v-model="form.utm_content" maxlength="200" /></el-form-item></el-form><template #footer><el-button :disabled="saving" @click="editorOpen = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template></el-dialog>
    <el-drawer v-model="statsOpen" title="近 30 天点击统计" size="min(660px, 94vw)"><template v-if="stats"><div class="stat-cards"><div><strong>{{ stats.counted_clicks }}</strong><span>有效点击</span></div><div><strong>{{ stats.unique_visitors }}</strong><span>独立访客</span></div><div><strong>{{ stats.filtered_clicks }}</strong><span>过滤点击</span></div></div><el-table :data="stats.daily" empty-text="当前周期暂无点击"><el-table-column prop="day" label="日期" /><el-table-column prop="counted_clicks" label="有效点击" /><el-table-column prop="unique_visitors" label="独立访客" /><el-table-column prop="filtered_clicks" label="已过滤" /></el-table><el-alert title="独立访客按不可逆 IP 摘要估算；10 分钟内重复点击和疑似机器人不会进入有效点击。" type="info" :closable="false" show-icon /></template></el-drawer>
  </section>
</template>

<style scoped>
.links-panel{overflow:hidden;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:24px;border-bottom:1px solid var(--color-border);background:linear-gradient(135deg,#f7f1e6,#edf3ef)}.panel-head p{margin:0 0 7px;color:var(--color-accent);font-size:10px;font-weight:800;letter-spacing:.17em}.panel-head h2{margin:0;font-family:var(--font-display);font-size:28px;font-weight:500}.panel-head span{display:block;margin-top:7px;color:var(--color-muted);font-size:12px}.actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}.actions :deep(.el-select){width:125px}.link-grid{display:grid;min-height:430px;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;padding:20px}.link-card{padding:18px;border:1px solid var(--color-border);border-radius:11px;background:#fffefa}.card-title{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.card-title small{color:var(--color-muted);font-size:10px}.card-title h3{margin:6px 0 0;font-family:var(--font-display);font-size:21px;font-weight:500}.metric{display:flex;align-items:baseline;gap:8px;margin:20px 0 12px}.metric strong{font-family:var(--font-display);font-size:35px}.metric span{color:var(--color-muted);font-size:11px}.link-card code{display:block;overflow:hidden;padding:9px;border-radius:7px;background:#edf2ed;color:#315344;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.link-card>p{overflow:hidden;margin:9px 0;color:var(--color-muted);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.utm{display:flex;min-height:25px;flex-wrap:wrap;gap:5px}.utm span{padding:4px 6px;border-radius:5px;background:#f4eee5;font-size:9px}.utm em{color:var(--color-muted);font-size:10px;font-style:normal}.link-card footer{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:14px;padding-top:10px;border-top:1px dashed var(--color-border)}.link-card footer small{color:var(--color-muted);font-size:9px}.suggestion-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px}.suggestion-grid article{display:flex;align-items:flex-start;flex-direction:column;padding:16px;border:1px solid var(--color-border);border-radius:9px}.suggestion-grid h3{margin:0;font-family:var(--font-display);font-size:19px}.suggestion-grid p{min-height:42px;color:var(--color-muted);font-size:12px;line-height:1.6}.suggestion-grid small{min-height:48px;color:var(--color-accent);font-size:9px;overflow-wrap:anywhere}.suggestion-grid .el-button{margin-top:auto}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 14px}.form-grid .wide{grid-column:1/-1}.stat-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px}.stat-cards div{display:flex;align-items:center;flex-direction:column;padding:17px;border-radius:9px;background:#edf2ed}.stat-cards strong{font-family:var(--font-display);font-size:28px}.stat-cards span{color:var(--color-muted);font-size:10px}.el-drawer .el-alert{margin-top:16px}@media(max-width:850px){.panel-head{flex-direction:column}.actions{justify-content:flex-start}.link-grid,.suggestion-grid{grid-template-columns:1fr}}@media(max-width:600px){.link-grid{padding:12px}.form-grid{grid-template-columns:1fr}.form-grid .wide{grid-column:auto}.link-card footer{align-items:flex-start;flex-direction:column}}
</style>
