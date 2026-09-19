<script setup lang="ts">
import { Plus, Refresh, Search } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import type { FormInstance, FormRules } from "element-plus"
import { computed, onMounted, reactive, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorMessage } from "../api/http"
import { createProduct, getProducts } from "../api/products"
import type { ProductPayload } from "../api/products"
import { getStores } from "../api/stores"
import DataTableShell from "../components/common/DataTableShell.vue"
import FormDialog from "../components/common/FormDialog.vue"
import PageHeader from "../components/common/PageHeader.vue"
import { useAuthStore } from "../stores/auth"
import type { Product, ProductStatus, Store, StorePlatform } from "../types/domain"
import { formatDate, formatMoney, platformLabels, platformOptions, productStatusLabels } from "../utils/domain"

interface ProductForm extends Omit<ProductPayload, "images"> { image_text: string }
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const products = ref<Product[]>([])
const stores = ref<Store[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const query = ref("")
const storeFilter = ref<number | "">("")
const platformFilter = ref<StorePlatform | "">("")
const statusFilter = ref<ProductStatus | "">("")
const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<ProductForm>({ store_id: 0, name: "", category: null, price: 0, cost: null, target_audience: null, selling_points: null, product_url: null, status: "draft", image_text: "" })
const canWrite = computed(() => authStore.can("product.write"))
const rules: FormRules<ProductForm> = {
  store_id: [{ required: true, message: "请选择所属店铺", trigger: "change" }],
  name: [{ required: true, message: "请输入商品名称", trigger: "blur" }],
  price: [{ required: true, message: "请输入售价", trigger: "blur" }],
}

async function loadProducts(): Promise<void> {
  loading.value = true
  try {
    const result = await getProducts({ page: page.value, page_size: pageSize.value, q: query.value.trim() || undefined, store_id: storeFilter.value || undefined, platform: platformFilter.value || undefined, status: statusFilter.value || undefined })
    products.value = result.items; total.value = result.total
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "商品列表加载失败")) }
  finally { loading.value = false }
}
async function loadStores(): Promise<void> {
  try { stores.value = (await getStores({ page: 1, page_size: 100, status: "active" })).items }
  catch { stores.value = [] }
}
function openCreate(): void {
  Object.assign(form, { store_id: stores.value[0]?.id ?? 0, name: "", category: null, price: 0, cost: null, target_audience: null, selling_points: null, product_url: null, status: "draft", image_text: "" })
  dialogVisible.value = true
}
async function submit(): Promise<void> {
  if (!await formRef.value?.validate().catch(() => false)) return
  saving.value = true
  try {
    const product = await createProduct({ store_id: form.store_id, name: form.name, category: form.category || null, price: Number(form.price), cost: form.cost === null ? null : Number(form.cost), target_audience: form.target_audience || null, selling_points: form.selling_points || null, product_url: form.product_url || null, images: form.image_text.split("\n").map((item) => item.trim()).filter(Boolean), status: form.status })
    ElMessage.success("商品创建成功")
    dialogVisible.value = false
    await router.push(`/products/${product.id}/overview`)
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "商品创建失败")) }
  finally { saving.value = false }
}
function search(): void { page.value = 1; void loadProducts() }
function resetFilters(): void { query.value = ""; storeFilter.value = ""; platformFilter.value = ""; statusFilter.value = ""; page.value = 1; void loadProducts() }
function changePage(value: number): void { page.value = value; void loadProducts() }
function changePageSize(value: number): void { pageSize.value = value; page.value = 1; void loadProducts() }
onMounted(() => {
  const initialStore = Number(route.query.store)
  if (Number.isInteger(initialStore) && initialStore > 0) storeFilter.value = initialStore
  void Promise.all([loadStores(), loadProducts()])
})
</script>

<template>
  <div>
    <PageHeader eyebrow="PRODUCT WORKSPACE" title="商品运营" description="以商品为核心串联店铺、平台映射、SKU 与库存；点击商品后进入统一的九标签运营工作区。">
      <template #actions><el-button v-if="canWrite" type="primary" :icon="Plus" @click="openCreate">创建商品</el-button></template>
    </PageHeader>
    <DataTableShell :loading="loading" :total="total" :page="page" :page-size="pageSize" empty-text="还没有符合条件的商品" @update:page="changePage" @update:page-size="changePageSize">
      <template #toolbar><div class="filters"><el-input v-model="query" clearable placeholder="搜索商品名称或分类" :prefix-icon="Search" @keyup.enter="search" /><el-select v-model="storeFilter" clearable filterable placeholder="全部店铺"><el-option v-for="store in stores" :key="store.id" :label="store.store_name" :value="store.id" /></el-select><el-select v-model="platformFilter" clearable placeholder="全部平台"><el-option v-for="item in platformOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select><el-select v-model="statusFilter" clearable placeholder="全部状态"><el-option label="草稿" value="draft" /><el-option label="上架" value="active" /><el-option label="下架" value="inactive" /></el-select><el-button type="primary" plain :icon="Search" @click="search">查询</el-button><el-button :icon="Refresh" @click="resetFilters">重置</el-button></div></template>
      <el-table v-if="products.length" :data="products" table-layout="fixed" @row-click="(row: Product) => router.push(`/products/${row.id}/overview`)">
        <el-table-column label="商品" min-width="250"><template #default="scope"><div class="product-cell"><el-image v-if="scope.row.images[0]" :src="scope.row.images[0]" fit="cover" /><span v-else>商</span><div><strong>{{ scope.row.name }}</strong><small>{{ scope.row.category || '未分类' }} · {{ scope.row.store_name }}</small></div></div></template></el-table-column>
        <el-table-column label="平台" width="100"><template #default="scope">{{ platformLabels[scope.row.platform as StorePlatform] }}</template></el-table-column>
        <el-table-column label="售价" width="120"><template #default="scope"><strong>{{ formatMoney(scope.row.price) }}</strong></template></el-table-column>
        <el-table-column label="映射" width="90"><template #default="scope">{{ scope.row.mapping_count }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="scope"><el-tag :type="scope.row.status === 'active' ? 'success' : scope.row.status === 'draft' ? 'warning' : 'info'" effect="plain">{{ productStatusLabels[scope.row.status as ProductStatus] }}</el-tag></template></el-table-column>
        <el-table-column label="最近诊断" min-width="165"><template #default="scope"><span class="muted">{{ formatDate(scope.row.last_diagnosis_at, '尚未诊断') }}</span></template></el-table-column>
        <el-table-column label="最近复盘" min-width="165"><template #default="scope"><span class="muted">{{ formatDate(scope.row.last_review_at, '尚未复盘') }}</span></template></el-table-column>
        <el-table-column label="操作" width="90" fixed="right"><template #default="scope"><el-button link type="primary" @click.stop="router.push(`/products/${scope.row.id}/overview`)">进入</el-button></template></el-table-column>
      </el-table>
    </DataTableShell>
    <FormDialog v-model="dialogVisible" title="创建商品" :loading="saving" width="720px" @confirm="submit">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <div class="form-grid"><el-form-item label="所属店铺" prop="store_id"><el-select v-model="form.store_id" filterable style="width: 100%"><el-option v-for="store in stores" :key="store.id" :label="store.store_name" :value="store.id" /></el-select></el-form-item><el-form-item label="商品名称" prop="name"><el-input v-model="form.name" /></el-form-item></div>
        <div class="form-grid"><el-form-item label="分类"><el-input v-model="form.category" /></el-form-item><el-form-item label="状态"><el-select v-model="form.status" style="width: 100%"><el-option label="草稿" value="draft" /><el-option label="上架" value="active" /><el-option label="下架" value="inactive" /></el-select></el-form-item></div>
        <div class="form-grid"><el-form-item label="售价" prop="price"><el-input-number v-model="form.price" :min="0" :precision="2" style="width: 100%" /></el-form-item><el-form-item label="成本"><el-input-number v-model="form.cost" :min="0" :precision="2" style="width: 100%" /></el-form-item></div>
        <el-form-item label="商品链接"><el-input v-model="form.product_url" placeholder="https://" /></el-form-item><el-form-item label="图片地址"><el-input v-model="form.image_text" type="textarea" :rows="3" placeholder="每行一个 HTTPS 图片地址" /></el-form-item>
      </el-form>
    </FormDialog>
  </div>
</template>

<style scoped>
.filters { display: grid; grid-template-columns: minmax(210px,1fr) 160px 130px 120px auto auto; gap: 10px; }
.product-cell { display: flex; gap: 12px; align-items: center; cursor: pointer; }.product-cell > span,.product-cell :deep(.el-image) { display: grid; width: 42px; height: 42px; flex: 0 0 auto; place-items: center; border-radius: 9px; background: #e8ece7; color: #607068; font-weight: 800; }.product-cell div { display:flex; overflow:hidden; flex-direction:column; }.product-cell strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.product-cell small,.muted { margin-top:3px; color:var(--color-muted); font-size:12px; }
.form-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }:deep(.el-table__row) { cursor:pointer; }
@media(max-width:1050px){.filters{grid-template-columns:1fr 1fr 1fr}}@media(max-width:620px){.filters,.form-grid{grid-template-columns:1fr}}
</style>
