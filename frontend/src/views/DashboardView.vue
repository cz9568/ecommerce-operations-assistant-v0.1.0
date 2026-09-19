<script setup lang="ts">
import { Bell, Connection, Goods, MagicStick, Plus, Refresh, Shop, TrendCharts } from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getDashboard } from "../api/dashboard"
import { getApiErrorMessage } from "../api/http"
import { initializeDemoData } from "../api/imports"
import PageHeader from "../components/common/PageHeader.vue"
import { useAuthStore } from "../stores/auth"
import type { DashboardData } from "../types/domain"
import { formatDate, platformLabels } from "../utils/domain"

const authStore = useAuthStore(); const router = useRouter()
const data = ref<DashboardData | null>(null); const platform = ref("")
const loading = ref(false); const seeding = ref(false)
const greeting = computed(() => authStore.user?.display_name || authStore.user?.username || "你好")
const canWrite = computed(() => authStore.can("product.write")); const canDemo = computed(() => authStore.can("settings.manage"))
function platformLabel(value: string): string { return (platformLabels as Record<string, string>)[value] || value }
const metrics = computed(() => data.value ? [
  { label: "商品总数", value: data.value.metrics.product_count, hint: `${data.value.metrics.store_count} 个店铺`, icon: Goods },
  { label: "进行中任务", value: data.value.metrics.active_job_count, hint: "等待中与生成中", icon: TrendCharts },
  { label: "待审核素材", value: data.value.metrics.pending_asset_count, hint: "需要人工确认", icon: MagicStick },
  { label: "复盘报告", value: data.value.metrics.review_report_count, hint: `${data.value.metrics.low_stock_count} 项低库存`, icon: Connection },
] : [])
async function load(): Promise<void> { loading.value = true; try { data.value = await getDashboard(platform.value) } catch (error) { ElMessage.error(getApiErrorMessage(error, "工作台加载失败")) } finally { loading.value = false } }
async function createDemo(): Promise<void> {
  await ElMessageBox.confirm("将创建带【演示】标识的完整闭环样例，重复执行不会复制数据。", "初始化演示数据", { type: "warning", confirmButtonText: "创建样例" })
  seeding.value = true
  try { const result = await initializeDemoData(); ElMessage.success(result.message); await load() }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "演示数据初始化失败")) }
  finally { seeding.value = false }
}
function openProduct(productId: number, tab = "overview"): void { void router.push({ name: "product-detail", params: { productId, tab } }) }
onMounted(() => void load())
</script>

<template>
  <div v-loading="loading" class="dashboard">
    <PageHeader eyebrow="TODAY'S OPERATIONS" :title="`${greeting}，开始今天的运营`" description="从库存预警、生成任务和最近复盘进入需要处理的单品，让每一步都有上下文。"><template #actions><el-select v-model="platform" clearable placeholder="全部平台" style="width:145px" @change="load"><el-option v-for="item in data?.available_platforms || []" :key="item" :label="platformLabel(item)" :value="item" /></el-select><el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button><el-button v-if="canWrite" type="primary" :icon="Plus" @click="router.push('/products')">创建商品</el-button></template></PageHeader>
    <section class="metric-grid"><article v-for="item in metrics" :key="item.label"><div class="metric-icon"><component :is="item.icon" /></div><p>{{ item.label }}</p><strong>{{ item.value }}</strong><small>{{ item.hint }}</small></article></section>
    <el-alert v-if="data?.metrics.low_stock_count" class="warning" type="warning" show-icon :closable="false" :title="`有 ${data.metrics.low_stock_count} 个 SKU 达到低库存阈值，请优先核对。`" />
    <section v-if="data && !data.metrics.product_count" class="empty-guide"><div><p>EMPTY WORKSPACE</p><h2>从第一条完整业务链开始</h2><span>可以创建真实店铺与商品，也可以由管理员初始化一套不会调用真实模型或平台的演示数据。</span></div><div><el-button v-if="canWrite" :icon="Shop" @click="router.push('/stores')">创建店铺</el-button><el-button v-if="canDemo" type="primary" :loading="seeding" @click="createDemo">初始化演示数据</el-button><el-tag v-else effect="plain">请联系管理员初始化演示数据</el-tag></div></section>
    <template v-if="data?.metrics.product_count">
      <section class="store-grid"><article v-for="item in data.stores" :key="item.id" @click="router.push(`/stores/${item.id}`)"><header><span>{{ platformLabel(item.platform) }}</span><el-tag :type="item.status === 'active' ? 'success' : 'info'">{{ item.status === 'active' ? '启用' : '停用' }}</el-tag></header><h3>{{ item.store_name }}</h3><div><span>商品 <b>{{ item.product_count }}</b></span><span>低库存 <b>{{ item.low_stock_count }}</b></span><span>进行中 <b>{{ item.active_job_count }}</b></span></div><small>最近复盘 {{ formatDate(item.latest_review_at) }}</small></article></section>
      <div class="workspace-grid"><section class="panel product-pool"><header><div><p>PRODUCT POOL</p><h2>商品池</h2></div><el-button text @click="router.push('/products')">查看全部</el-button></header><button v-for="item in data.products" :key="item.id" @click="openProduct(item.id)"><span><b>{{ item.name }}</b><small>{{ item.store_name }} · {{ platformLabel(item.platform) }}</small></span><span class="signals"><el-tag v-if="item.low_stock_count" type="warning">{{ item.low_stock_count }} 低库存</el-tag><el-tag v-if="item.latest_job_status" effect="plain">{{ item.latest_job_status }}</el-tag><small>复盘 {{ formatDate(item.latest_review_at) }}</small></span></button></section><section class="panel alerts"><header><div><p>ATTENTION</p><h2>库存预警</h2></div><Bell /></header><el-empty v-if="!data.low_stock.length" description="当前没有低库存项" :image-size="58" /><button v-for="item in data.low_stock" :key="item.sku_id" @click="router.push({ name: 'product-detail', params: { productId: item.product_id, tab: 'overview' }, query: { sku: item.sku_id } })"><span><b>{{ item.product_name }}</b><small>{{ item.sku_code }}</small></span><strong>{{ item.available_qty }}<small> / 阈值 {{ item.warning_threshold }}</small></strong></button></section></div>
      <div class="workspace-grid lower"><section class="panel"><header><div><p>RECENT JOBS</p><h2>最近生成任务</h2></div></header><button v-for="item in data.recent_jobs" :key="item.id" @click="openProduct(item.product_id, 'tasks')"><span><b>{{ item.product_name }}</b><small>{{ item.job_kind }} · {{ formatDate(item.created_at) }}</small></span><el-tag>{{ item.job_status }} · {{ item.progress_percent }}%</el-tag></button><el-empty v-if="!data.recent_jobs.length" description="暂无生成任务" :image-size="50" /></section><section class="panel"><header><div><p>RECENT REVIEWS</p><h2>最近运营复盘</h2></div></header><button v-for="item in data.recent_reviews" :key="item.id" @click="router.push({ name: 'product-detail', params: { productId: item.product_id, tab: 'reviews' }, query: { review: item.id } })"><span><b>{{ item.product_name }}</b><small>{{ item.period_start }} 至 {{ item.period_end }}</small></span><strong>ROI {{ item.roi ?? '—' }}</strong></button><el-empty v-if="!data.recent_reviews.length" description="暂无复盘报告" :image-size="50" /></section></div>
    </template>
  </div>
</template>

<style scoped>
.dashboard{display:flex;flex-direction:column;gap:20px}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--color-border);border-radius:12px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.metric-grid article{position:relative;min-height:155px;padding:22px;border-right:1px solid var(--color-border)}.metric-grid article:last-child{border:0}.metric-icon{position:absolute;top:20px;right:20px;width:32px;color:#9ca69f}.metric-grid p{margin:0 0 17px;color:var(--color-muted);font-size:12px}.metric-grid strong{display:block;font-family:var(--font-display);font-size:42px;font-weight:500}.metric-grid small{color:#9aa19d}.warning{margin:0}.empty-guide{display:flex;align-items:center;justify-content:space-between;padding:35px;border:1px solid var(--color-border);border-radius:14px;background:linear-gradient(135deg,#f7efe5,#edf4ef)}.empty-guide p,.panel header p{margin:0;color:var(--color-accent);font-size:10px;font-weight:800;letter-spacing:.16em}.empty-guide h2,.panel h2{margin:7px 0;font-family:var(--font-display);font-size:27px;font-weight:500}.empty-guide span{color:var(--color-muted)}.store-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.store-grid article{padding:18px;border:1px solid var(--color-border);border-radius:11px;background:var(--color-surface);cursor:pointer}.store-grid article:hover{border-color:#bfb3a3;transform:translateY(-1px)}.store-grid header,.panel header{display:flex;align-items:center;justify-content:space-between}.store-grid header>span,.store-grid small{color:var(--color-muted);font-size:10px}.store-grid h3{margin:18px 0;font-family:var(--font-display);font-size:20px;font-weight:500}.store-grid article>div{display:flex;gap:18px;margin-bottom:14px;color:var(--color-muted);font-size:11px}.store-grid b{color:var(--color-ink)}.workspace-grid{display:grid;grid-template-columns:2fr 1fr;gap:16px}.workspace-grid.lower{grid-template-columns:1fr 1fr}.panel{overflow:hidden;padding:20px;border:1px solid var(--color-border);border-radius:12px;background:var(--color-surface);box-shadow:var(--shadow-soft)}.panel header{margin-bottom:12px}.panel header svg{width:22px;color:var(--color-accent)}.panel h2{font-size:23px}.panel>button{display:flex;width:100%;align-items:center;justify-content:space-between;gap:14px;padding:13px 5px;border:0;border-bottom:1px solid var(--color-border);background:none;text-align:left;cursor:pointer}.panel>button:hover{background:#faf8f3}.panel>button span{display:flex;min-width:0;flex-direction:column}.panel>button b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.panel>button small{margin-top:4px;color:var(--color-muted);font-size:10px}.signals{align-items:flex-end!important;flex-direction:row!important;gap:6px}.alerts>button strong{color:#ad4d37;font-family:var(--font-display);font-size:21px}.alerts>button strong small{font-family:var(--font-body);font-weight:400}@media(max-width:1050px){.metric-grid,.store-grid{grid-template-columns:repeat(2,1fr)}.workspace-grid,.workspace-grid.lower{grid-template-columns:1fr}}@media(max-width:650px){.metric-grid,.store-grid{grid-template-columns:1fr}.metric-grid article{border-right:0;border-bottom:1px solid var(--color-border)}.empty-guide{align-items:flex-start;flex-direction:column;gap:20px}.signals{display:none!important}}
</style>
