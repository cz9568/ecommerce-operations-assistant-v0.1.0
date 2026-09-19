<script setup lang="ts">
import { ArrowLeft, Edit, Plus, Refresh } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorMessage } from "../api/http"
import { getInventory } from "../api/inventory"
import { getProducts } from "../api/products"
import {
  createPlatformAccount, generateInventoryAdvice, getLatestInventoryAdvice, getPlatformAccounts,
  getStore, getStoreSummary, revokePlatformAuthorization, startPlatformAuthorization,
  updatePlatformAccount, updateStore,
} from "../api/stores"
import type { AdviceGeneratePayload, StorePayload } from "../api/stores"
import FormDialog from "../components/common/FormDialog.vue"
import PageHeader from "../components/common/PageHeader.vue"
import { useAuthStore } from "../stores/auth"
import type { AdviceAction, AdvicePriority, AuthorizationStatus, Inventory, InventoryAdviceRun, PlatformAccount, Product, Store, StoreSummary } from "../types/domain"
import { adviceActionLabels, advicePriorityLabels, authStatusLabels, entityStatusLabels, formatDate, platformLabels, platformOptions } from "../utils/domain"

const route = useRoute(); const router = useRouter(); const authStore = useAuthStore()
const storeId = computed(() => Number(route.params.storeId))
const store = ref<Store | null>(null); const summary = ref<StoreSummary | null>(null)
const products = ref<Product[]>([]); const inventory = ref<Inventory[]>([]); const lowStock = ref<Inventory[]>([])
const accounts = ref<PlatformAccount[]>([]); const advice = ref<InventoryAdviceRun | null>(null)
const loading = ref(false); const activeTab = ref(String(route.query.tab || "overview"))
const storeDialog = ref(false); const accountDialog = ref(false); const adviceDialog = ref(false); const saving = ref(false)
const editingAccount = ref<PlatformAccount | null>(null)
const storeForm = reactive<StorePayload>({ store_name: "", platform: "taobao", external_store_id: null, owner_user_id: null, status: "active", remark: null })
const accountForm = reactive({ account_name: "", remark: "" })
const adviceForm = reactive<AdviceGeneratePayload>({ lookback_days: 30, coverage_days: 14, safety_multiplier: 1.2, min_outbound_events: 2 })
const canManage = computed(() => authStore.can("store.manage")); const canInventory = computed(() => authStore.can("inventory.write"))

async function loadAll(): Promise<void> {
  if (!Number.isInteger(storeId.value) || storeId.value < 1) return
  loading.value = true
  try {
    const [storeValue, summaryValue, productPage, inventoryPage, lowStockPage, accountList] = await Promise.all([
      getStore(storeId.value), getStoreSummary(storeId.value), getProducts({ page: 1, page_size: 100, store_id: storeId.value }),
      getInventory({ page: 1, page_size: 100, store_id: storeId.value }), getInventory({ page: 1, page_size: 100, store_id: storeId.value }, true), getPlatformAccounts(storeId.value),
    ])
    store.value = storeValue; summary.value = summaryValue; products.value = productPage.items; inventory.value = inventoryPage.items; lowStock.value = lowStockPage.items; accounts.value = accountList
    try { advice.value = await getLatestInventoryAdvice(storeId.value) } catch { advice.value = null }
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "店铺详情加载失败")) }
  finally { loading.value = false }
}
function openStoreEdit(): void {
  if (!store.value) return
  Object.assign(storeForm, { store_name: store.value.store_name, platform: store.value.platform, external_store_id: store.value.external_store_id, owner_user_id: store.value.owner_user_id, status: store.value.status, remark: store.value.remark })
  storeDialog.value = true
}
async function saveStore(): Promise<void> {
  saving.value = true
  try { store.value = await updateStore(storeId.value, storeForm); storeDialog.value = false; ElMessage.success("店铺信息已更新") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "店铺保存失败")) }
  finally { saving.value = false }
}
function openAccount(account?: PlatformAccount): void {
  editingAccount.value = account || null; accountForm.account_name = ""; accountForm.remark = account?.remark || ""; accountDialog.value = true
}
async function saveAccount(): Promise<void> {
  if (!editingAccount.value && !accountForm.account_name.trim()) { ElMessage.warning("请输入账号标识"); return }
  saving.value = true
  try {
    if (editingAccount.value) {
      const payload: { account_name?: string; remark?: string | null } = { remark: accountForm.remark || null }
      if (accountForm.account_name.trim()) payload.account_name = accountForm.account_name.trim()
      await updatePlatformAccount(editingAccount.value.id, payload)
    } else await createPlatformAccount(storeId.value, { account_name: accountForm.account_name.trim(), remark: accountForm.remark || null })
    accountDialog.value = false; accounts.value = await getPlatformAccounts(storeId.value); ElMessage.success("平台账号已保存")
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "平台账号保存失败")) }
  finally { saving.value = false }
}
async function startAuthorization(account: PlatformAccount): Promise<void> {
  try { await startPlatformAuthorization(account.id); accounts.value = await getPlatformAccounts(storeId.value); ElMessage.success("已创建授权占位流程") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "启动授权失败")) }
}
async function revokeAuthorization(account: PlatformAccount): Promise<void> {
  await ElMessageBox.confirm("确定撤销这个平台账号的授权状态吗？", "撤销授权", { type: "warning" })
  try { await revokePlatformAuthorization(account.id); accounts.value = await getPlatformAccounts(storeId.value); ElMessage.success("授权已撤销") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "撤销授权失败")) }
}
async function generateAdvice(): Promise<void> {
  saving.value = true
  try { advice.value = await generateInventoryAdvice(storeId.value, adviceForm); adviceDialog.value = false; ElMessage.success("库存建议已生成") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "库存建议生成失败")) }
  finally { saving.value = false }
}
function toProduct(productId: number, skuId?: number): void { void router.push({ path: `/products/${productId}/overview`, query: skuId ? { sku: String(skuId) } : undefined }) }
function changeTab(name: string | number): void { void router.replace({ query: { ...route.query, tab: String(name) } }) }
watch(() => route.query.tab, (value) => { activeTab.value = String(value || "overview") })
onMounted(loadAll)
</script>

<template>
  <div v-loading="loading">
    <el-button text :icon="ArrowLeft" class="back" @click="router.push('/stores')">返回店铺列表</el-button>
    <PageHeader :eyebrow="store ? platformLabels[store.platform] : 'STORE'" :title="store?.store_name || '店铺详情'" :description="store?.remark || '查看店铺商品、库存风险、平台账号与库存建议。'">
      <template #actions><el-button v-if="canManage" :icon="Edit" @click="openStoreEdit">编辑店铺</el-button></template>
    </PageHeader>
    <div v-if="summary" class="metrics">
      <div><small>商品</small><strong>{{ summary.product_count }}</strong></div><div><small>SKU</small><strong>{{ summary.sku_count }}</strong></div><div :class="{ alert: summary.low_stock_count }"><small>低库存预警</small><strong>{{ summary.low_stock_count }}</strong></div><div><small>平台账号</small><strong>{{ summary.authorized_account_count }}/{{ summary.platform_account_count }}</strong></div>
    </div>
    <el-tabs v-model="activeTab" class="store-tabs" @tab-change="changeTab">
      <el-tab-pane label="经营概览" name="overview">
        <div class="overview-grid">
          <section class="panel"><div class="panel-title"><div><h3>店铺资料</h3><p>用于商品归属与渠道识别</p></div></div><el-descriptions v-if="store" :column="1" border><el-descriptions-item label="平台">{{ platformLabels[store.platform] }}</el-descriptions-item><el-descriptions-item label="外部编号">{{ store.external_store_id || '未填写' }}</el-descriptions-item><el-descriptions-item label="负责人">{{ store.owner_name || '未分配' }}</el-descriptions-item><el-descriptions-item label="状态">{{ entityStatusLabels[store.status] }}</el-descriptions-item><el-descriptions-item label="更新时间">{{ formatDate(store.updated_at) }}</el-descriptions-item></el-descriptions></section>
          <section class="panel"><div class="panel-title"><div><h3>低库存预警</h3><p>点击条目可追溯到具体商品与 SKU</p></div><el-button link type="primary" @click="activeTab = 'inventory'; changeTab('inventory')">查看全部</el-button></div><div v-if="lowStock.length" class="warning-list"><button v-for="item in lowStock.slice(0, 5)" :key="item.sku_id" @click="toProduct(item.product_id, item.sku_id)"><span><strong>{{ item.product_name }}</strong><small>{{ item.sku_code }} · 可用 {{ item.available_qty }}</small></span><el-tag type="danger">阈值 {{ item.warning_threshold }}</el-tag></button></div><el-empty v-else description="当前没有低库存预警" :image-size="60" /></section>
        </div>
      </el-tab-pane>
      <el-tab-pane label="商品" name="products">
        <section class="panel"><div class="panel-title"><div><h3>店铺商品</h3><p>共 {{ products.length }} 个商品</p></div><el-button type="primary" plain @click="router.push({ path: '/products', query: { store: storeId } })">商品工作台</el-button></div><el-table :data="products"><el-table-column prop="name" label="商品" min-width="220" /><el-table-column prop="category" label="分类" /><el-table-column prop="mapping_count" label="平台映射" width="100" /><el-table-column prop="status" label="状态" width="90" /><el-table-column label="操作" width="90"><template #default="scope"><el-button link type="primary" @click="toProduct(scope.row.id)">进入</el-button></template></el-table-column></el-table></section>
      </el-tab-pane>
      <el-tab-pane label="库存" name="inventory">
        <section class="panel"><div class="panel-title"><div><h3>库存概览</h3><p>库存数据可继续下钻到 SKU 流水</p></div><el-button :icon="Refresh" @click="loadAll">刷新</el-button></div><el-table :data="inventory"><el-table-column prop="product_name" label="商品" min-width="180" /><el-table-column label="SKU" min-width="170"><template #default="scope"><strong>{{ scope.row.sku_code }}</strong><br><small>{{ scope.row.sku_name }}</small></template></el-table-column><el-table-column prop="stock_qty" label="现货" width="80" /><el-table-column prop="locked_qty" label="锁定" width="80" /><el-table-column prop="available_qty" label="可用" width="80" /><el-table-column label="预警" width="100"><template #default="scope"><el-tag v-if="scope.row.is_low_stock" type="danger">低库存</el-tag><span v-else>正常</span></template></el-table-column><el-table-column label="操作" width="100"><template #default="scope"><el-button link type="primary" @click="toProduct(scope.row.product_id, scope.row.sku_id)">库存详情</el-button></template></el-table-column></el-table></section>
      </el-tab-pane>
      <el-tab-pane label="平台账号" name="accounts">
        <section class="panel"><div class="panel-title"><div><h3>平台账号</h3><p>当前为安全占位授权流程，不展示敏感凭证</p></div><el-button v-if="canManage" type="primary" :icon="Plus" @click="openAccount()">添加账号</el-button></div><div v-if="accounts.length" class="account-grid"><article v-for="account in accounts" :key="account.id"><div><el-tag :type="account.auth_status === 'authorized' ? 'success' : account.auth_status === 'failed' ? 'danger' : 'warning'">{{ authStatusLabels[account.auth_status as AuthorizationStatus] }}</el-tag><small>{{ platformLabels[account.platform] }}</small></div><h4>{{ account.account_name_masked }}</h4><p>{{ account.remark || '暂无备注' }}</p><footer v-if="canManage"><el-button link @click="openAccount(account)">编辑</el-button><el-button link type="primary" @click="startAuthorization(account)">发起授权</el-button><el-button v-if="account.auth_status === 'authorized'" link type="danger" @click="revokeAuthorization(account)">撤销</el-button></footer></article></div><el-empty v-else description="尚未配置平台账号" /></section>
      </el-tab-pane>
      <el-tab-pane label="库存建议" name="advice">
        <section class="panel"><div class="panel-title"><div><h3>库存建议</h3><p>{{ advice ? `生成于 ${formatDate(advice.generated_at)}` : '尚未生成建议快照' }}</p></div><el-button v-if="canInventory" type="primary" @click="adviceDialog = true">生成建议</el-button></div><template v-if="advice"><div class="advice-summary"><span>SKU {{ advice.item_count }}</span><span>建议补货 {{ advice.replenish_count }}</span><span>数据不足 {{ advice.insufficient_count }}</span><span>规则 {{ advice.rule_version }}</span></div><el-table :data="advice.items"><el-table-column prop="product_name" label="商品" min-width="180" /><el-table-column label="SKU" min-width="160"><template #default="scope">{{ scope.row.sku_code }}<br><small>{{ scope.row.sku_name }}</small></template></el-table-column><el-table-column prop="available_qty" label="可用" width="80" /><el-table-column prop="target_stock_qty" label="目标" width="80" /><el-table-column prop="suggested_restock_qty" label="建议补货" width="100" /><el-table-column label="动作" width="110"><template #default="scope"><el-tag :type="scope.row.action === 'replenish' ? 'danger' : scope.row.action === 'monitor' ? 'warning' : 'success'">{{ adviceActionLabels[scope.row.action as AdviceAction] }}</el-tag></template></el-table-column><el-table-column label="优先级" width="90"><template #default="scope">{{ advicePriorityLabels[scope.row.priority as AdvicePriority] }}</template></el-table-column><el-table-column label="说明" min-width="260"><template #default="scope"><span class="explanation">{{ scope.row.explanation }}</span></template></el-table-column><el-table-column label="操作" width="90"><template #default="scope"><el-button link type="primary" @click="toProduct(scope.row.product_id, scope.row.sku_id)">追溯</el-button></template></el-table-column></el-table></template><el-empty v-else description="生成后会形成可追溯的库存建议快照" /></section>
      </el-tab-pane>
    </el-tabs>

    <FormDialog v-model="storeDialog" title="编辑店铺" :loading="saving" @confirm="saveStore"><el-form :model="storeForm" label-position="top"><div class="form-grid"><el-form-item label="店铺名称"><el-input v-model="storeForm.store_name" /></el-form-item><el-form-item label="平台"><el-select v-model="storeForm.platform" disabled style="width:100%"><el-option v-for="item in platformOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></div><div class="form-grid"><el-form-item label="平台店铺编号"><el-input v-model="storeForm.external_store_id" /></el-form-item><el-form-item label="状态"><el-radio-group v-model="storeForm.status"><el-radio-button value="active">启用</el-radio-button><el-radio-button value="inactive">停用</el-radio-button></el-radio-group></el-form-item></div><el-form-item label="备注"><el-input v-model="storeForm.remark" type="textarea" :rows="3" /></el-form-item></el-form></FormDialog>
    <FormDialog v-model="accountDialog" :title="editingAccount ? '编辑平台账号' : '添加平台账号'" :loading="saving" @confirm="saveAccount"><el-form label-position="top"><el-form-item :label="editingAccount ? '新账号标识（不修改可留空）' : '账号标识'"><el-input v-model="accountForm.account_name" /></el-form-item><el-form-item label="备注"><el-input v-model="accountForm.remark" type="textarea" :rows="3" /></el-form-item></el-form></FormDialog>
    <FormDialog v-model="adviceDialog" title="生成库存建议" :loading="saving" @confirm="generateAdvice"><el-form :model="adviceForm" label-position="top"><div class="form-grid"><el-form-item label="回看天数"><el-input-number v-model="adviceForm.lookback_days" :min="7" :max="90" /></el-form-item><el-form-item label="目标覆盖天数"><el-input-number v-model="adviceForm.coverage_days" :min="1" :max="90" /></el-form-item><el-form-item label="安全系数"><el-input-number v-model="adviceForm.safety_multiplier" :min="1" :max="3" :step="0.1" :precision="2" /></el-form-item><el-form-item label="最少出库事件"><el-input-number v-model="adviceForm.min_outbound_events" :min="1" :max="20" /></el-form-item></div></el-form></FormDialog>
  </div>
</template>

<style scoped>
.back{margin-bottom:14px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px}.metrics>div{display:flex;flex-direction:column;padding:19px 20px;border:1px solid var(--color-border);border-radius:12px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.metrics small{color:var(--color-muted)}.metrics strong{margin-top:8px;font-family:var(--font-display);font-size:28px;font-weight:500}.metrics .alert strong{color:#c33f32}.store-tabs{--el-tabs-header-height:52px}.panel{padding:22px;border:1px solid var(--color-border);border-radius:12px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.overview-grid{display:grid;grid-template-columns:minmax(300px,.75fr) minmax(420px,1.25fr);gap:18px}.panel-title{display:flex;gap:20px;align-items:flex-start;justify-content:space-between;margin-bottom:18px}.panel-title h3{margin:0;font-family:var(--font-display);font-size:22px;font-weight:500}.panel-title p{margin:5px 0 0;color:var(--color-muted);font-size:12px}.warning-list{display:flex;flex-direction:column}.warning-list button{display:flex;align-items:center;justify-content:space-between;padding:13px 4px;border:0;border-bottom:1px solid var(--color-border);background:none;cursor:pointer;text-align:left}.warning-list span{display:flex;flex-direction:column}.warning-list small,.panel small{margin-top:4px;color:var(--color-muted)}.account-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}.account-grid article{padding:18px;border:1px solid var(--color-border);border-radius:10px;background:#faf9f4}.account-grid article>div{display:flex;align-items:center;justify-content:space-between}.account-grid h4{margin:16px 0 8px}.account-grid p{min-height:36px;margin:0;color:var(--color-muted);font-size:12px}.account-grid footer{margin-top:12px}.advice-summary{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px}.advice-summary span{padding:8px 12px;border-radius:8px;background:#f2eee5;color:#5d665f;font-size:12px}.explanation{font-size:12px;line-height:1.55}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:900px){.metrics{grid-template-columns:1fr 1fr}.overview-grid{grid-template-columns:1fr}}@media(max-width:560px){.metrics,.form-grid{grid-template-columns:1fr}}
</style>
