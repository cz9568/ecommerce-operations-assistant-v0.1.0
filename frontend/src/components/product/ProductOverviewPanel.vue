<script setup lang="ts">
import { Edit, Plus } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { computed, onMounted, reactive, ref, watch } from "vue"

import { getApiErrorMessage } from "../../api/http"
import { createProductMapping, deleteProductMapping, getProductMappings, updateProduct, updateProductMapping } from "../../api/products"
import type { MappingPayload } from "../../api/products"
import { useAuthStore } from "../../stores/auth"
import type { MappingStatus, Product, ProductMapping, StorePlatform } from "../../types/domain"
import { formatMoney, mappingStatusLabels, platformLabels } from "../../utils/domain"
import FormDialog from "../common/FormDialog.vue"
import CompetitorPanel from "./CompetitorPanel.vue"
import SkuInventoryPanel from "./SkuInventoryPanel.vue"

const props = defineProps<{ product: Product; focusSkuId?: number }>()
const emit = defineEmits<{ updated: [product: Product]; dirty: [value: boolean] }>()
const authStore = useAuthStore(); const canWrite = computed(() => authStore.can("product.write"))
const mappings = ref<ProductMapping[]>([]); const mappingLoading = ref(false); const saving = ref(false)
const productDialog = ref(false); const mappingDialog = ref(false); const editingMapping = ref<ProductMapping | null>(null); const skuDirty = ref(false)
const competitorDirty = ref(false)
const productForm = reactive({ name: "", category: "", price: 0, cost: null as number | null, target_audience: "", selling_points: "", product_url: "", image_text: "" })
const mappingForm = reactive<MappingPayload>({ platform_product_id: "", platform_sku_id: "", mapping_status: "active" })
watch([productDialog, mappingDialog, skuDirty, competitorDirty], (values) => emit("dirty", values.some(Boolean)))
async function loadMappings(): Promise<void> {
  mappingLoading.value = true
  try { mappings.value = await getProductMappings(props.product.id) }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "平台映射加载失败")) }
  finally { mappingLoading.value = false }
}
function openProductEdit(): void {
  Object.assign(productForm, { name: props.product.name, category: props.product.category || "", price: Number(props.product.price), cost: props.product.cost === null ? null : Number(props.product.cost), target_audience: props.product.target_audience || "", selling_points: props.product.selling_points || "", product_url: props.product.product_url || "", image_text: props.product.images.join("\n") }); productDialog.value = true
}
async function saveProduct(): Promise<void> {
  if (!productForm.name.trim()) { ElMessage.warning("请输入商品名称"); return }
  saving.value = true
  try {
    const updated = await updateProduct(props.product.id, { name: productForm.name.trim(), category: productForm.category || null, price: Number(productForm.price), cost: productForm.cost, target_audience: productForm.target_audience || null, selling_points: productForm.selling_points || null, product_url: productForm.product_url || null, images: productForm.image_text.split("\n").map((item) => item.trim()).filter(Boolean) })
    productDialog.value = false; emit("updated", updated); ElMessage.success("商品资料已更新")
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "商品保存失败")) }
  finally { saving.value = false }
}
function openMapping(mapping?: ProductMapping): void {
  editingMapping.value = mapping || null; Object.assign(mappingForm, mapping ? { platform_product_id: mapping.platform_product_id, platform_sku_id: mapping.platform_sku_id, mapping_status: mapping.mapping_status } : { platform_product_id: "", platform_sku_id: "", mapping_status: "active" }); mappingDialog.value = true
}
async function saveMapping(): Promise<void> {
  if (!mappingForm.platform_product_id.trim()) { ElMessage.warning("请输入平台商品编号"); return }
  saving.value = true
  try {
    if (editingMapping.value) await updateProductMapping(props.product.id, editingMapping.value.id, mappingForm)
    else await createProductMapping(props.product.id, mappingForm)
    mappingDialog.value = false; await loadMappings(); ElMessage.success(editingMapping.value ? "映射已更新" : "映射已创建")
  } catch (error) { ElMessage.error(getApiErrorMessage(error, "平台映射保存失败")) }
  finally { saving.value = false }
}
async function removeMapping(mapping: ProductMapping): Promise<void> {
  await ElMessageBox.confirm(`确定删除平台商品映射 ${mapping.platform_product_id} 吗？`, "删除映射", { type: "warning" })
  try { await deleteProductMapping(props.product.id, mapping.id); await loadMappings(); ElMessage.success("映射已删除") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "映射删除失败")) }
}
onMounted(loadMappings); watch(() => props.product.id, loadMappings)
</script>

<template>
  <div class="overview-stack">
    <section class="panel">
      <div class="panel-title"><div><h3>商品资料</h3><p>基础资料与渠道商品链接</p></div><el-button v-if="canWrite" :icon="Edit" @click="openProductEdit">编辑</el-button></div>
      <div class="product-summary"><el-image v-if="product.images[0]" :src="product.images[0]" fit="cover" /><div v-else class="image-placeholder">商</div><el-descriptions :column="2" border><el-descriptions-item label="所属店铺">{{ product.store_name }}</el-descriptions-item><el-descriptions-item label="平台">{{ platformLabels[product.platform] }}</el-descriptions-item><el-descriptions-item label="分类">{{ product.category || '未分类' }}</el-descriptions-item><el-descriptions-item label="售价">{{ formatMoney(product.price) }}</el-descriptions-item><el-descriptions-item label="成本">{{ formatMoney(product.cost) }}</el-descriptions-item><el-descriptions-item label="商品链接"><el-link v-if="product.product_url" :href="product.product_url" target="_blank" type="primary">打开链接</el-link><span v-else>未填写</span></el-descriptions-item><el-descriptions-item label="目标人群" :span="2">{{ product.target_audience || '未填写' }}</el-descriptions-item><el-descriptions-item label="核心卖点" :span="2">{{ product.selling_points || '未填写' }}</el-descriptions-item></el-descriptions></div>
    </section>
    <section class="panel">
      <div class="panel-title"><div><h3>平台映射</h3><p>关联平台商品与平台 SKU 编号</p></div><el-button v-if="canWrite" type="primary" plain :icon="Plus" @click="openMapping()">新增映射</el-button></div>
      <el-table v-loading="mappingLoading" :data="mappings"><el-table-column label="平台" width="100"><template #default="scope">{{ platformLabels[scope.row.platform as StorePlatform] }}</template></el-table-column><el-table-column prop="platform_product_id" label="平台商品编号" min-width="180" /><el-table-column label="平台 SKU 编号" min-width="180"><template #default="scope">{{ scope.row.platform_sku_id || '全部 SKU' }}</template></el-table-column><el-table-column label="状态" width="100"><template #default="scope"><el-tag :type="scope.row.mapping_status === 'active' ? 'success' : scope.row.mapping_status === 'invalid' ? 'danger' : 'info'">{{ mappingStatusLabels[scope.row.mapping_status as MappingStatus] }}</el-tag></template></el-table-column><el-table-column v-if="canWrite" label="操作" width="130"><template #default="scope"><el-button link @click="openMapping(scope.row as ProductMapping)">编辑</el-button><el-button link type="danger" @click="removeMapping(scope.row as ProductMapping)">删除</el-button></template></el-table-column></el-table>
      <el-empty v-if="!mappings.length && !mappingLoading" description="尚未建立平台映射" :image-size="60" />
    </section>
    <CompetitorPanel :product-id="product.id" @dirty="competitorDirty = $event" />
    <SkuInventoryPanel :product-id="product.id" :focus-sku-id="focusSkuId" @dirty="skuDirty = $event" />

    <FormDialog v-model="productDialog" title="编辑商品资料" :loading="saving" width="760px" @confirm="saveProduct"><el-form :model="productForm" label-position="top"><div class="form-grid"><el-form-item label="商品名称" required><el-input v-model="productForm.name" /></el-form-item><el-form-item label="分类"><el-input v-model="productForm.category" /></el-form-item></div><div class="form-grid"><el-form-item label="售价"><el-input-number v-model="productForm.price" :min="0" :precision="2" style="width:100%" /></el-form-item><el-form-item label="成本"><el-input-number v-model="productForm.cost" :min="0" :precision="2" style="width:100%" /></el-form-item></div><el-form-item label="商品链接"><el-input v-model="productForm.product_url" /></el-form-item><el-form-item label="目标人群"><el-input v-model="productForm.target_audience" type="textarea" :rows="2" /></el-form-item><el-form-item label="核心卖点"><el-input v-model="productForm.selling_points" type="textarea" :rows="3" /></el-form-item><el-form-item label="图片地址"><el-input v-model="productForm.image_text" type="textarea" :rows="3" placeholder="每行一个 HTTPS 图片地址" /></el-form-item></el-form></FormDialog>
    <FormDialog v-model="mappingDialog" :title="editingMapping ? '编辑平台映射' : '新增平台映射'" :loading="saving" @confirm="saveMapping"><el-form :model="mappingForm" label-position="top"><el-form-item label="平台商品编号" required><el-input v-model="mappingForm.platform_product_id" /></el-form-item><el-form-item label="平台 SKU 编号"><el-input v-model="mappingForm.platform_sku_id" placeholder="留空表示商品级映射" /></el-form-item><el-form-item label="映射状态"><el-select v-model="mappingForm.mapping_status" style="width:100%"><el-option label="有效" value="active" /><el-option label="停用" value="inactive" /><el-option label="失效" value="invalid" /></el-select></el-form-item></el-form></FormDialog>
  </div>
</template>

<style scoped>
.overview-stack{display:flex;flex-direction:column;gap:18px}.panel{padding:22px;border:1px solid var(--color-border);border-radius:12px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.panel-title{display:flex;gap:20px;align-items:flex-start;justify-content:space-between;margin-bottom:18px}.panel-title h3{margin:0;font-family:var(--font-display);font-size:22px;font-weight:500}.panel-title p{margin:5px 0 0;color:var(--color-muted);font-size:12px}.product-summary{display:grid;grid-template-columns:180px 1fr;gap:18px}.product-summary :deep(.el-image),.image-placeholder{display:grid;width:180px;height:180px;place-items:center;border-radius:10px;background:#edf0eb;color:#718079;font-family:var(--font-display);font-size:44px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:720px){.product-summary,.form-grid{grid-template-columns:1fr}.product-summary :deep(.el-image),.image-placeholder{width:100%;height:220px}}
</style>
