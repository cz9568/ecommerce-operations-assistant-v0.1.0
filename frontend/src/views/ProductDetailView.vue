<script setup lang="ts">
import { ArrowLeft, MoreFilled } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router"

import { getApiErrorMessage } from "../api/http"
import { archiveProduct, getProduct, updateProductStatus } from "../api/products"
import ProductOverviewPanel from "../components/product/ProductOverviewPanel.vue"
import DiagnosisPanel from "../components/product/DiagnosisPanel.vue"
import CreativePlanPanel from "../components/product/CreativePlanPanel.vue"
import GenerationJobsPanel from "../components/product/GenerationJobsPanel.vue"
import AssetLibraryPanel from "../components/product/AssetLibraryPanel.vue"
import AdvertisingPanel from "../components/product/AdvertisingPanel.vue"
import PromotionLinksPanel from "../components/product/PromotionLinksPanel.vue"
import ReviewPanel from "../components/product/ReviewPanel.vue"
import PageHeader from "../components/common/PageHeader.vue"
import { useAuthStore } from "../stores/auth"
import type { Product, ProductStatus } from "../types/domain"
import { formatDate, platformLabels, productStatusLabels } from "../utils/domain"

const TABS = [
  { key: "overview", label: "商品&竞品", eyebrow: "PRODUCT FOUNDATION", title: "商品、竞品、SKU 与库存", description: "商品资料、平台映射、竞品解析与监控、SKU、库存调整和流水已形成可追溯的基础工作区。" },
  { key: "diagnosis", label: "诊断", eyebrow: "DIAGNOSIS", title: "经营诊断", description: "基于商品、竞品与库存快照生成可编辑、可追溯的结构化诊断。" },
  { key: "main-images", label: "主图", eyebrow: "CREATIVE", title: "主图工作区", description: "生成、编辑并选择可追溯的主图创意方向。" },
  { key: "video", label: "视频", eyebrow: "VIDEO", title: "视频工作区", description: "生成、编辑并选择包含完整分镜与口播的视频脚本。" },
  { key: "tasks", label: "生成任务", eyebrow: "GENERATION JOBS", title: "图片与视频生成任务", description: "跟踪异步生成进度、事件和失败原因，并在合法状态下取消或重试。" },
  { key: "assets", label: "素材库", eyebrow: "ASSET LIBRARY", title: "商品素材库", description: "预览生成图片与视频，管理版本、场景、评分、标签、备注和审核状态。" },
  { key: "links", label: "链接", eyebrow: "PROMOTION LINKS", title: "推广链接", description: "生成场景建议、创建安全追踪链接并查看过滤后的点击统计。" },
  { key: "ads", label: "投放", eyebrow: "ADVERTISING", title: "投放建议与实验", description: "选择已审核素材和有效链接生成建议，由人工确认并管理实验计划。" },
  { key: "reviews", label: "复盘", eyebrow: "REVIEW", title: "经营数据与运营复盘", description: "核对周期指标，沉淀复盘版本并从下一步动作开启新一轮诊断。" },
] as const
const route = useRoute(); const router = useRouter(); const authStore = useAuthStore()
const product = ref<Product | null>(null); const loading = ref(false); const dirty = ref(false)
const productId = computed(() => Number(route.params.productId)); const activeTab = computed(() => String(route.params.tab || "overview"))
const currentTab = computed(() => TABS.find((item) => item.key === activeTab.value) || TABS[0])
const canWrite = computed(() => authStore.can("product.write")); const focusSkuId = computed(() => route.query.sku ? Number(route.query.sku) : undefined)
async function loadProduct(): Promise<void> {
  if (!Number.isInteger(productId.value) || productId.value < 1) return
  loading.value = true
  try { product.value = await getProduct(productId.value) }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "商品详情加载失败")) }
  finally { loading.value = false }
}
async function selectTab(key: string): Promise<void> {
  if (key === activeTab.value) return
  if (dirty.value) {
    try { await ElMessageBox.confirm("当前编辑内容尚未保存，切换标签页会丢失这些修改。", "离开当前编辑", { confirmButtonText: "放弃并离开", cancelButtonText: "继续编辑", type: "warning" }) }
    catch { return }
    dirty.value = false
  }
  await router.push({ name: "product-detail", params: { productId: productId.value, tab: key } })
}
async function changeStatus(status: "active" | "inactive"): Promise<void> {
  if (!product.value) return
  try { product.value = await updateProductStatus(product.value.id, status); ElMessage.success(status === "active" ? "商品已上架" : "商品已下架") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "商品状态更新失败")) }
}
async function archive(): Promise<void> {
  if (!product.value) return
  await ElMessageBox.confirm("归档后商品将变为停用状态，历史 SKU 与库存流水仍会保留。", "归档商品", { type: "warning", confirmButtonText: "确认归档" })
  try { await archiveProduct(product.value.id); ElMessage.success("商品已归档"); await router.push("/products") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "商品归档失败")) }
}
function beforeUnload(event: BeforeUnloadEvent): void { if (dirty.value) { event.preventDefault(); event.returnValue = "" } }
onBeforeRouteLeave((_to, _from, next) => {
  if (!dirty.value) { next(); return }
  ElMessageBox.confirm("当前编辑内容尚未保存，确定离开吗？", "离开商品工作区", { confirmButtonText: "放弃并离开", cancelButtonText: "继续编辑", type: "warning" }).then(() => { dirty.value = false; next() }).catch(() => next(false))
})
watch([productId, activeTab], ([id, tab], [oldId]) => {
  if (!TABS.some((item) => item.key === tab)) { void router.replace({ name: "product-detail", params: { productId: id, tab: "overview" } }); return }
  if (id !== oldId) { product.value = null; void loadProduct() }
})
onMounted(() => {
  window.addEventListener("beforeunload", beforeUnload)
  if (!TABS.some((item) => item.key === activeTab.value)) void router.replace({ name: "product-detail", params: { productId: productId.value, tab: "overview" } })
  else void loadProduct()
})
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload))
</script>

<template>
  <div v-loading="loading">
    <el-button text :icon="ArrowLeft" class="back" @click="router.push('/products')">返回商品列表</el-button>
    <PageHeader v-if="product" :eyebrow="`${platformLabels[product.platform]} · ${product.store_name}`" :title="product.name" :description="`状态：${productStatusLabels[product.status as ProductStatus]} · 最近更新 ${formatDate(product.updated_at)}`">
      <template #actions><el-dropdown v-if="canWrite" trigger="click"><el-button :icon="MoreFilled">商品操作</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item v-if="product.status !== 'active'" @click="changeStatus('active')">上架商品</el-dropdown-item><el-dropdown-item v-if="product.status === 'active'" @click="changeStatus('inactive')">下架商品</el-dropdown-item><el-dropdown-item divided @click="archive">归档商品</el-dropdown-item></el-dropdown-menu></template></el-dropdown></template>
    </PageHeader>
    <nav class="product-tabs" aria-label="商品运营标签页"><button v-for="tab in TABS" :key="tab.key" type="button" :class="{ active: activeTab === tab.key }" @click="selectTab(tab.key)">{{ tab.label }}</button></nav>
    <ProductOverviewPanel v-if="product && activeTab === 'overview'" :product="product" :focus-sku-id="focusSkuId" @updated="product = $event" @dirty="dirty = $event" />
    <DiagnosisPanel v-else-if="product && activeTab === 'diagnosis'" :product-id="product.id" @dirty="dirty = $event" />
    <CreativePlanPanel v-else-if="product && activeTab === 'main-images'" :product-id="product.id" plan-type="main_image" @dirty="dirty = $event" />
    <CreativePlanPanel v-else-if="product && activeTab === 'video'" :product-id="product.id" plan-type="video_script" @dirty="dirty = $event" />
    <GenerationJobsPanel v-else-if="product && activeTab === 'tasks'" :product-id="product.id" />
    <AssetLibraryPanel v-else-if="product && activeTab === 'assets'" :product-id="product.id" />
    <PromotionLinksPanel v-else-if="product && activeTab === 'links'" :product-id="product.id" @dirty="dirty = $event" />
    <AdvertisingPanel v-else-if="product && activeTab === 'ads'" :product-id="product.id" @dirty="dirty = $event" />
    <ReviewPanel v-else-if="product && activeTab === 'reviews'" :product-id="product.id" @dirty="dirty = $event" />
    <section v-else-if="product" class="placeholder-panel"><p>{{ currentTab.eyebrow }}</p><h2>{{ currentTab.title }}</h2><span>{{ currentTab.description }}</span><div class="placeholder-flow"><div><b>01</b><strong>输入与数据</strong><small>保留当前商品上下文</small></div><i /><div><b>02</b><strong>处理与审核</strong><small>记录过程、版本和责任人</small></div><i /><div><b>03</b><strong>结果与追溯</strong><small>回到商品形成闭环</small></div></div><el-tag effect="plain">功能骨架已就绪 · 后续里程碑接入</el-tag></section>
  </div>
</template>

<style scoped>
.back{margin-bottom:14px}.product-tabs{display:flex;overflow-x:auto;gap:4px;margin:-4px 0 20px;padding:6px;border:1px solid var(--color-border);border-radius:12px;background:rgb(255 253 248 / 72%)}.product-tabs button{min-width:max-content;padding:10px 15px;border:0;border-radius:8px;background:none;color:var(--color-muted);cursor:pointer;font-size:13px;font-weight:650}.product-tabs button:hover{color:var(--color-ink)}.product-tabs button.active{background:#17221e;color:white;box-shadow:0 6px 14px rgb(23 34 30 / 15%)}.placeholder-panel{display:flex;min-height:420px;align-items:center;flex-direction:column;justify-content:center;padding:50px 24px;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);text-align:center;box-shadow:var(--shadow-soft)}.placeholder-panel>p{margin:0;color:var(--color-accent);font-size:10px;font-weight:800;letter-spacing:.18em}.placeholder-panel h2{margin:12px 0 8px;font-family:var(--font-display);font-size:34px;font-weight:500}.placeholder-panel>span{max-width:600px;color:var(--color-muted);line-height:1.7}.placeholder-flow{display:flex;align-items:center;margin:36px 0}.placeholder-flow div{display:flex;width:170px;flex-direction:column}.placeholder-flow b{color:var(--color-accent);font-family:var(--font-display);font-size:22px}.placeholder-flow strong{margin-top:8px}.placeholder-flow small{margin-top:5px;color:var(--color-muted)}.placeholder-flow i{width:42px;height:1px;background:var(--color-border)}@media(max-width:700px){.placeholder-flow{align-items:stretch;flex-direction:column;gap:14px}.placeholder-flow i{width:1px;height:18px;margin:auto}}
</style>
