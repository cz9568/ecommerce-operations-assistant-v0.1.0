<script setup lang="ts">
import { Plus, Refresh, Search } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import { computed, onMounted, reactive, ref, watch } from "vue"

import { getApiErrorMessage } from "../../api/http"
import { adjustInventory, createSku, getInventoryMovements, getSkuInventory, getSkus, updateInventoryConfig, updateSku, updateSkuStatus } from "../../api/inventory"
import type { SkuPayload } from "../../api/inventory"
import { useAuthStore } from "../../stores/auth"
import type { EntityStatus, Inventory, InventoryMovement, InventoryMovementType, ProductSku } from "../../types/domain"
import { entityStatusLabels, formatDate, formatMoney, formatSpecs, movementTypeLabels } from "../../utils/domain"
import FormDialog from "../common/FormDialog.vue"

const props = defineProps<{ productId: number; focusSkuId?: number }>()
const emit = defineEmits<{ dirty: [value: boolean] }>()
const authStore = useAuthStore(); const canWrite = computed(() => authStore.can("inventory.write"))
const skus = ref<ProductSku[]>([]); const inventories = ref<Record<number, Inventory>>({}); const total = ref(0)
const page = ref(1); const pageSize = ref(20); const query = ref(""); const statusFilter = ref<EntityStatus | "">(""); const loading = ref(false); const saving = ref(false)
const skuDialog = ref(false); const adjustmentDialog = ref(false); const configDialog = ref(false); const movementDrawer = ref(false)
const editingSku = ref<ProductSku | null>(null); const selectedSku = ref<ProductSku | null>(null); const selectedInventory = ref<Inventory | null>(null)
const movements = ref<InventoryMovement[]>([]); const movementTotal = ref(0); const movementPage = ref(1); const movementLoading = ref(false); const movementFilter = ref<InventoryMovementType | "">("")
const skuForm = reactive({ sku_code: "", sku_name: "", specs_text: "{}", price: 0, cost: null as number | null, status: "active" as EntityStatus, platform_sku_id: "" })
const adjustmentForm = reactive({ movement_type: "inbound" as InventoryMovementType, quantity: 1, reason_text: "", reference_type: "", reference_id: "" })
const configForm = reactive({ warning_threshold: 0, location_text: "" })

watch([skuDialog, adjustmentDialog, configDialog], (values) => emit("dirty", values.some(Boolean)))
async function loadSkus(): Promise<void> {
  loading.value = true
  try {
    const result = await getSkus(props.productId, { page: page.value, page_size: pageSize.value, q: query.value.trim() || undefined, status: statusFilter.value || undefined })
    skus.value = result.items; total.value = result.total
    const settled = await Promise.allSettled(result.items.map((sku) => getSkuInventory(props.productId, sku.id)))
    const next: Record<number, Inventory> = {}
    settled.forEach((result) => { if (result.status === "fulfilled") next[result.value.sku_id] = result.value })
    inventories.value = next
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "SKU 列表加载失败")) }
  finally { loading.value = false }
}
function openSku(sku?: ProductSku): void {
  editingSku.value = sku || null
  Object.assign(skuForm, sku ? { sku_code: sku.sku_code, sku_name: sku.sku_name, specs_text: JSON.stringify(sku.specs, null, 2), price: Number(sku.price), cost: sku.cost === null ? null : Number(sku.cost), status: sku.status, platform_sku_id: sku.platform_sku_id || "" } : { sku_code: "", sku_name: "", specs_text: "{}", price: 0, cost: null, status: "active", platform_sku_id: "" })
  skuDialog.value = true
}
function parseSpecs(): Record<string, string> | null {
  try {
    const value: unknown = JSON.parse(skuForm.specs_text || "{}")
    if (!value || Array.isArray(value) || typeof value !== "object" || Object.values(value).some((item) => typeof item !== "string")) throw new Error()
    return value as Record<string, string>
  } catch { ElMessage.warning("规格请填写为 JSON 对象，例如 {\"颜色\":\"红色\"}"); return null }
}
async function saveSku(): Promise<void> {
  if (!skuForm.sku_code.trim() || !skuForm.sku_name.trim()) { ElMessage.warning("请填写 SKU 编码和名称"); return }
  const specs = parseSpecs(); if (!specs) return
  saving.value = true
  try {
    const payload: SkuPayload = { sku_code: skuForm.sku_code.trim(), sku_name: skuForm.sku_name.trim(), specs, price: Number(skuForm.price), cost: skuForm.cost, status: skuForm.status, platform_sku_id: skuForm.platform_sku_id || null }
    if (editingSku.value) await updateSku(props.productId, editingSku.value.id, payload)
    else await createSku(props.productId, payload)
    skuDialog.value = false; await loadSkus(); ElMessage.success(editingSku.value ? "SKU 已更新" : "SKU 已创建")
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "SKU 保存失败")) }
  finally { saving.value = false }
}
async function toggleSku(sku: ProductSku): Promise<void> {
  try { await updateSkuStatus(props.productId, sku.id, sku.status === "active" ? "inactive" : "active"); await loadSkus(); ElMessage.success("SKU 状态已更新") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "状态更新失败")) }
}
function openAdjustment(sku: ProductSku): void {
  const inventory = inventories.value[sku.id]; if (!inventory) { ElMessage.warning("库存数据尚未就绪，请刷新后重试"); return }
  selectedSku.value = sku; selectedInventory.value = inventory; Object.assign(adjustmentForm, { movement_type: "inbound", quantity: 1, reason_text: "", reference_type: "", reference_id: "" }); adjustmentDialog.value = true
}
async function saveAdjustment(): Promise<void> {
  if (!selectedSku.value || !selectedInventory.value || !adjustmentForm.reason_text.trim()) { ElMessage.warning("请填写调整原因"); return }
  let changeQty = Number(adjustmentForm.quantity)
  if (["outbound", "unlock"].includes(adjustmentForm.movement_type)) changeQty = -Math.abs(changeQty)
  if (["inbound", "lock"].includes(adjustmentForm.movement_type)) changeQty = Math.abs(changeQty)
  saving.value = true
  try {
    const result = await adjustInventory(props.productId, selectedSku.value.id, { movement_type: adjustmentForm.movement_type, change_qty: changeQty, reason_text: adjustmentForm.reason_text.trim(), reference_type: adjustmentForm.reference_type || undefined, reference_id: adjustmentForm.reference_id || undefined, expected_version: selectedInventory.value.version_no })
    inventories.value = { ...inventories.value, [selectedSku.value.id]: result.inventory }; selectedInventory.value = result.inventory; adjustmentDialog.value = false
    ElMessage.success("库存调整成功")
    if (movementDrawer.value) await loadMovements()
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "库存调整失败，请刷新库存后重试")) }
  finally { saving.value = false }
}
function openConfig(sku: ProductSku): void {
  const inventory = inventories.value[sku.id]; if (!inventory) return
  selectedSku.value = sku; selectedInventory.value = inventory; configForm.warning_threshold = inventory.warning_threshold; configForm.location_text = inventory.location_text || ""; configDialog.value = true
}
async function saveConfig(): Promise<void> {
  if (!selectedSku.value || !selectedInventory.value) return
  saving.value = true
  try {
    const result = await updateInventoryConfig(props.productId, selectedSku.value.id, { warning_threshold: configForm.warning_threshold, location_text: configForm.location_text || null, expected_version: selectedInventory.value.version_no })
    inventories.value = { ...inventories.value, [selectedSku.value.id]: result }; configDialog.value = false; ElMessage.success("库存配置已更新")
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "库存配置更新失败，请刷新后重试")) }
  finally { saving.value = false }
}
async function openMovements(sku: ProductSku): Promise<void> {
  selectedSku.value = sku; movementPage.value = 1; movementFilter.value = ""; movementDrawer.value = true; await loadMovements()
}
async function loadMovements(): Promise<void> {
  if (!selectedSku.value) return
  movementLoading.value = true
  try { const result = await getInventoryMovements(props.productId, selectedSku.value.id, { page: movementPage.value, page_size: 20, movement_type: movementFilter.value || undefined }); movements.value = result.items; movementTotal.value = result.total }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "库存流水加载失败")) }
  finally { movementLoading.value = false }
}
function search(): void { page.value = 1; void loadSkus() }
onMounted(loadSkus)
watch(() => props.productId, () => { page.value = 1; void loadSkus() })
</script>

<template>
  <section class="panel">
    <div class="panel-title"><div><h3>SKU 与库存</h3><p>库存调整成功后会立即刷新；流水永久保留业务原因与引用编号</p></div><el-button v-if="canWrite" type="primary" :icon="Plus" @click="openSku()">新增 SKU</el-button></div>
    <div class="toolbar"><el-input v-model="query" clearable placeholder="搜索 SKU 编码或名称" :prefix-icon="Search" @keyup.enter="search" /><el-select v-model="statusFilter" clearable placeholder="全部状态"><el-option label="启用" value="active" /><el-option label="停用" value="inactive" /></el-select><el-button type="primary" plain :icon="Search" @click="search">查询</el-button><el-button :icon="Refresh" @click="loadSkus">刷新</el-button></div>
    <el-table v-loading="loading" :data="skus" row-key="id" :row-class-name="({ row }: { row: ProductSku }) => row.id === focusSkuId ? 'focus-row' : ''">
      <el-table-column label="SKU" min-width="210"><template #default="scope"><strong>{{ scope.row.sku_code }}</strong><div class="subtle">{{ scope.row.sku_name }}</div></template></el-table-column>
      <el-table-column label="规格" min-width="180"><template #default="scope"><span class="subtle">{{ formatSpecs(scope.row.specs) }}</span></template></el-table-column>
      <el-table-column label="价格" width="110"><template #default="scope">{{ formatMoney(scope.row.price) }}</template></el-table-column>
      <el-table-column label="库存" min-width="190"><template #default="scope"><div v-if="inventories[scope.row.id]" class="stock"><span>现货 <b>{{ inventories[scope.row.id].stock_qty }}</b></span><span>锁定 <b>{{ inventories[scope.row.id].locked_qty }}</b></span><span>可用 <b>{{ inventories[scope.row.id].available_qty }}</b></span></div><span v-else class="subtle">加载中</span></template></el-table-column>
      <el-table-column label="预警" width="100"><template #default="scope"><el-tag v-if="inventories[scope.row.id]?.is_low_stock" type="danger">低库存</el-tag><span v-else>正常</span></template></el-table-column>
      <el-table-column label="状态" width="90"><template #default="scope"><el-tag :type="scope.row.status === 'active' ? 'success' : 'info'" effect="plain">{{ entityStatusLabels[scope.row.status as EntityStatus] }}</el-tag></template></el-table-column>
      <el-table-column label="操作" min-width="260" fixed="right"><template #default="scope"><el-button link type="primary" @click="openMovements(scope.row as ProductSku)">流水</el-button><template v-if="canWrite"><el-button link @click="openAdjustment(scope.row as ProductSku)">调整库存</el-button><el-button link @click="openConfig(scope.row as ProductSku)">配置</el-button><el-dropdown><el-button link>更多</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="openSku(scope.row as ProductSku)">编辑 SKU</el-dropdown-item><el-dropdown-item @click="toggleSku(scope.row as ProductSku)">{{ scope.row.status === 'active' ? '停用' : '启用' }}</el-dropdown-item></el-dropdown-menu></template></el-dropdown></template></template></el-table-column>
    </el-table>
    <div v-if="total > pageSize" class="pager"><el-pagination background layout="prev, pager, next" :current-page="page" :page-size="pageSize" :total="total" @update:current-page="(value:number) => { page = value; loadSkus() }" /></div>

    <FormDialog v-model="skuDialog" :title="editingSku ? '编辑 SKU' : '新增 SKU'" :loading="saving" width="680px" @confirm="saveSku"><el-form :model="skuForm" label-position="top"><div class="form-grid"><el-form-item label="SKU 编码" required><el-input v-model="skuForm.sku_code" placeholder="如 TS-RED-M" /></el-form-item><el-form-item label="SKU 名称" required><el-input v-model="skuForm.sku_name" /></el-form-item></div><div class="form-grid"><el-form-item label="售价"><el-input-number v-model="skuForm.price" :min="0" :precision="2" style="width:100%" /></el-form-item><el-form-item label="成本"><el-input-number v-model="skuForm.cost" :min="0" :precision="2" style="width:100%" /></el-form-item></div><el-form-item label="规格（JSON 对象）"><el-input v-model="skuForm.specs_text" type="textarea" :rows="4" /></el-form-item><div class="form-grid"><el-form-item label="平台 SKU 编号"><el-input v-model="skuForm.platform_sku_id" /></el-form-item><el-form-item label="状态"><el-select v-model="skuForm.status" style="width:100%"><el-option label="启用" value="active" /><el-option label="停用" value="inactive" /></el-select></el-form-item></div></el-form></FormDialog>
    <FormDialog v-model="adjustmentDialog" :title="`调整库存 · ${selectedSku?.sku_code || ''}`" :loading="saving" @confirm="saveAdjustment"><el-alert v-if="selectedInventory" type="info" :closable="false" :title="`当前现货 ${selectedInventory.stock_qty}，锁定 ${selectedInventory.locked_qty}，可用 ${selectedInventory.available_qty}`" /><el-form :model="adjustmentForm" label-position="top" class="dialog-form"><div class="form-grid"><el-form-item label="业务动作"><el-select v-model="adjustmentForm.movement_type" style="width:100%"><el-option v-for="(label,key) in movementTypeLabels" :key="key" :label="label" :value="key" /></el-select></el-form-item><el-form-item :label="adjustmentForm.movement_type === 'adjustment' ? '变更量（可正可负）' : '数量'"><el-input-number v-model="adjustmentForm.quantity" :min="adjustmentForm.movement_type === 'adjustment' ? -2000000000 : 1" style="width:100%" /></el-form-item></div><el-form-item label="调整原因" required><el-input v-model="adjustmentForm.reason_text" type="textarea" :rows="3" placeholder="例如采购入库、订单出库或盘点差异" /></el-form-item><div class="form-grid"><el-form-item label="引用类型"><el-input v-model="adjustmentForm.reference_type" placeholder="选填，如 order" /></el-form-item><el-form-item label="引用编号"><el-input v-model="adjustmentForm.reference_id" placeholder="与引用类型同时填写" /></el-form-item></div></el-form></FormDialog>
    <FormDialog v-model="configDialog" :title="`库存配置 · ${selectedSku?.sku_code || ''}`" :loading="saving" @confirm="saveConfig"><el-form :model="configForm" label-position="top"><el-form-item label="低库存预警阈值"><el-input-number v-model="configForm.warning_threshold" :min="0" style="width:100%" /></el-form-item><el-form-item label="库位"><el-input v-model="configForm.location_text" placeholder="例如 A-01-03" /></el-form-item></el-form></FormDialog>
    <el-drawer v-model="movementDrawer" :title="`库存流水 · ${selectedSku?.sku_code || ''}`" size="min(760px, 92vw)"><div class="movement-filter"><el-select v-model="movementFilter" clearable placeholder="全部动作" @change="movementPage = 1; loadMovements()"><el-option v-for="(label,key) in movementTypeLabels" :key="key" :label="label" :value="key" /></el-select><el-button :icon="Refresh" @click="loadMovements">刷新</el-button></div><el-table v-loading="movementLoading" :data="movements"><el-table-column label="动作" width="100"><template #default="scope">{{ movementTypeLabels[scope.row.movement_type as InventoryMovementType] }}</template></el-table-column><el-table-column label="变更" width="90"><template #default="scope"><b :class="scope.row.change_qty > 0 ? 'positive' : 'negative'">{{ scope.row.change_qty > 0 ? '+' : '' }}{{ scope.row.change_qty }}</b></template></el-table-column><el-table-column label="前 → 后" width="110"><template #default="scope">{{ scope.row.before_qty }} → {{ scope.row.after_qty }}</template></el-table-column><el-table-column prop="reason_text" label="原因" min-width="180" /><el-table-column label="时间" min-width="160"><template #default="scope">{{ formatDate(scope.row.created_at) }}</template></el-table-column></el-table><el-pagination v-if="movementTotal > 20" class="pager" background layout="prev,pager,next" :current-page="movementPage" :page-size="20" :total="movementTotal" @update:current-page="(value:number) => { movementPage = value; loadMovements() }" /></el-drawer>
  </section>
</template>

<style scoped>
.panel{padding:22px;border:1px solid var(--color-border);border-radius:12px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.panel-title{display:flex;gap:20px;align-items:flex-start;justify-content:space-between;margin-bottom:18px}.panel-title h3{margin:0;font-family:var(--font-display);font-size:22px;font-weight:500}.panel-title p{margin:5px 0 0;color:var(--color-muted);font-size:12px}.toolbar{display:grid;grid-template-columns:minmax(220px,1fr) 130px auto auto;gap:10px;margin-bottom:16px}.subtle{margin-top:4px;color:var(--color-muted);font-size:12px}.stock{display:flex;gap:10px;font-size:12px}.stock span{padding:5px 7px;border-radius:6px;background:#f1f3ef}.stock b{margin-left:3px}.pager{display:flex;justify-content:flex-end;margin-top:18px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.dialog-form{margin-top:18px}.movement-filter{display:flex;gap:10px;margin-bottom:16px}.positive{color:#278453}.negative{color:#c33f32}:deep(.focus-row>td.el-table__cell){background:#fff2e9!important}:deep(.focus-row>td:first-child){box-shadow:inset 3px 0 var(--color-accent)}
@media(max-width:700px){.toolbar,.form-grid{grid-template-columns:1fr}.stock{flex-direction:column;gap:3px}}
</style>
