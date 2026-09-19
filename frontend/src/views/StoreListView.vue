<script setup lang="ts">
import { Plus, Refresh, Search } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import type { FormInstance, FormRules } from "element-plus"
import { computed, onMounted, reactive, ref } from "vue"
import { useRouter } from "vue-router"

import { createStore, getStores, updateStore } from "../api/stores"
import type { StorePayload } from "../api/stores"
import { getApiErrorMessage } from "../api/http"
import DataTableShell from "../components/common/DataTableShell.vue"
import FormDialog from "../components/common/FormDialog.vue"
import PageHeader from "../components/common/PageHeader.vue"
import { useAuthStore } from "../stores/auth"
import type { EntityStatus, Store, StorePlatform } from "../types/domain"
import { entityStatusLabels, formatDate, platformLabels, platformOptions } from "../utils/domain"

const router = useRouter()
const authStore = useAuthStore()
const stores = ref<Store[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const query = ref("")
const platformFilter = ref<StorePlatform | "">("")
const statusFilter = ref<EntityStatus | "">("")
const dialogVisible = ref(false)
const saving = ref(false)
const editingStore = ref<Store | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<StorePayload>(emptyForm())

const canManage = computed(() => authStore.can("store.manage"))
const dialogTitle = computed(() => editingStore.value ? `编辑店铺 · ${editingStore.value.store_name}` : "创建店铺")
const rules: FormRules<StorePayload> = {
  store_name: [{ required: true, message: "请输入店铺名称", trigger: "blur" }],
  platform: [{ required: true, message: "请选择平台", trigger: "change" }],
  status: [{ required: true, message: "请选择状态", trigger: "change" }],
}

function emptyForm(): StorePayload {
  return { store_name: "", platform: "taobao", external_store_id: null, status: "active", remark: null }
}
async function loadStores(): Promise<void> {
  loading.value = true
  try {
    const result = await getStores({ page: page.value, page_size: pageSize.value, q: query.value.trim() || undefined, platform: platformFilter.value || undefined, status: statusFilter.value || undefined })
    stores.value = result.items
    total.value = result.total
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "店铺列表加载失败")) }
  finally { loading.value = false }
}
function openCreate(): void {
  editingStore.value = null
  Object.assign(form, emptyForm())
  dialogVisible.value = true
}
function openEdit(store: Store): void {
  editingStore.value = store
  Object.assign(form, { store_name: store.store_name, platform: store.platform, external_store_id: store.external_store_id, owner_user_id: store.owner_user_id, status: store.status, remark: store.remark })
  dialogVisible.value = true
}
async function submit(): Promise<void> {
  if (!await formRef.value?.validate().catch(() => false)) return
  saving.value = true
  try {
    if (editingStore.value) await updateStore(editingStore.value.id, form)
    else await createStore(form)
    ElMessage.success(editingStore.value ? "店铺信息已更新" : "店铺创建成功")
    dialogVisible.value = false
    await loadStores()
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "店铺保存失败")) }
  finally { saving.value = false }
}
function search(): void { page.value = 1; void loadStores() }
function resetFilters(): void { query.value = ""; platformFilter.value = ""; statusFilter.value = ""; page.value = 1; void loadStores() }
function changePage(value: number): void { page.value = value; void loadStores() }
function changePageSize(value: number): void { pageSize.value = value; page.value = 1; void loadStores() }

onMounted(loadStores)
</script>

<template>
  <div>
    <PageHeader eyebrow="COMMERCE PORTFOLIO" title="店铺管理" description="集中查看各渠道店铺、商品规模与库存风险；进入详情后可继续追踪 SKU、平台账号和库存建议。">
      <template #actions><el-button v-if="canManage" type="primary" :icon="Plus" @click="openCreate">创建店铺</el-button></template>
    </PageHeader>
    <DataTableShell :loading="loading" :total="total" :page="page" :page-size="pageSize" empty-text="还没有符合条件的店铺" @update:page="changePage" @update:page-size="changePageSize">
      <template #toolbar>
        <div class="filters">
          <el-input v-model="query" clearable placeholder="搜索店铺名称或外部编号" :prefix-icon="Search" @keyup.enter="search" />
          <el-select v-model="platformFilter" clearable placeholder="全部平台"><el-option v-for="item in platformOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          <el-select v-model="statusFilter" clearable placeholder="全部状态"><el-option label="启用" value="active" /><el-option label="停用" value="inactive" /></el-select>
          <el-button type="primary" plain :icon="Search" @click="search">查询</el-button><el-button :icon="Refresh" @click="resetFilters">重置</el-button>
        </div>
      </template>
      <el-table v-if="stores.length" :data="stores" table-layout="fixed" @row-click="(row: Store) => router.push(`/stores/${row.id}`)">
        <el-table-column label="店铺" min-width="220"><template #default="scope"><div class="store-cell"><span>{{ platformLabels[scope.row.platform as StorePlatform].slice(0, 1) }}</span><div><strong>{{ scope.row.store_name }}</strong><small>{{ platformLabels[scope.row.platform as StorePlatform] }} · {{ scope.row.external_store_id || '未填写外部编号' }}</small></div></div></template></el-table-column>
        <el-table-column label="负责人" min-width="120"><template #default="scope">{{ scope.row.owner_name || '未分配' }}</template></el-table-column>
        <el-table-column prop="product_count" label="商品" width="90" />
        <el-table-column label="低库存" width="110"><template #default="scope"><el-tag :type="scope.row.low_stock_count ? 'danger' : 'success'" effect="light">{{ scope.row.low_stock_count }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="scope"><el-tag :type="scope.row.status === 'active' ? 'success' : 'info'" effect="plain">{{ entityStatusLabels[scope.row.status as EntityStatus] }}</el-tag></template></el-table-column>
        <el-table-column label="更新时间" min-width="165"><template #default="scope"><span class="muted">{{ formatDate(scope.row.updated_at) }}</span></template></el-table-column>
        <el-table-column label="操作" width="140" fixed="right"><template #default="scope"><el-button link type="primary" @click.stop="router.push(`/stores/${scope.row.id}`)">详情</el-button><el-button v-if="canManage" link @click.stop="openEdit(scope.row as Store)">编辑</el-button></template></el-table-column>
      </el-table>
    </DataTableShell>
    <FormDialog v-model="dialogVisible" :title="dialogTitle" :loading="saving" @confirm="submit">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <div class="form-grid"><el-form-item label="店铺名称" prop="store_name"><el-input v-model="form.store_name" /></el-form-item><el-form-item label="所属平台" prop="platform"><el-select v-model="form.platform" :disabled="Boolean(editingStore)" style="width: 100%"><el-option v-for="item in platformOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></div>
        <div class="form-grid"><el-form-item label="平台店铺编号"><el-input v-model="form.external_store_id" placeholder="选填" /></el-form-item><el-form-item label="状态" prop="status"><el-radio-group v-model="form.status"><el-radio-button value="active">启用</el-radio-button><el-radio-button value="inactive">停用</el-radio-button></el-radio-group></el-form-item></div>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="3" /></el-form-item>
      </el-form>
    </FormDialog>
  </div>
</template>

<style scoped>
.filters { display: grid; grid-template-columns: minmax(220px, 1fr) 150px 130px auto auto; gap: 10px; }
.store-cell { display: flex; gap: 12px; align-items: center; cursor: pointer; }
.store-cell > span { display: grid; width: 38px; height: 38px; flex: 0 0 auto; place-items: center; border-radius: 11px; background: #efe5d7; color: #9b4d30; font-weight: 800; }
.store-cell div { display: flex; overflow: hidden; flex-direction: column; }.store-cell strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.store-cell small,.muted { margin-top: 3px; color: var(--color-muted); font-size: 12px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
:deep(.el-table__row) { cursor: pointer; }
@media (max-width: 900px) { .filters { grid-template-columns: 1fr 1fr; } }
@media (max-width: 560px) { .filters,.form-grid { grid-template-columns: 1fr; } }
</style>
