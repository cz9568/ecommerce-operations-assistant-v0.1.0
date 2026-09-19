<script setup lang="ts">
import { Refresh, Search } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorMessage } from "../api/http"
import { getProducts } from "../api/products"
import DataTableShell from "../components/common/DataTableShell.vue"
import PageHeader from "../components/common/PageHeader.vue"
import type { Product, ProductStatus, StorePlatform } from "../types/domain"
import { formatDate, platformLabels, productStatusLabels } from "../utils/domain"

interface WorkspaceAction {
  label: string
  tab: "tasks" | "assets" | "links" | "ads" | "reviews"
  primary?: boolean
}

const route = useRoute()
const router = useRouter()
const products = ref<Product[]>([])
const loading = ref(false)
const query = ref("")
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const isTaskWorkspace = computed(() => route.name === "task-assets")
const pageCopy = computed(() => isTaskWorkspace.value
  ? {
      eyebrow: "GENERATION WORKSPACE",
      title: "任务与素材",
      description: "选择商品后查看图片与视频生成任务、执行进度、事件时间线及已落库素材。",
    }
  : {
      eyebrow: "GROWTH WORKSPACE",
      title: "投放与复盘",
      description: "选择商品后管理推广链接、投放建议、人工实验、经营数据与复盘报告。",
    })
const actions = computed<WorkspaceAction[]>(() => isTaskWorkspace.value
  ? [
      { label: "生成任务", tab: "tasks", primary: true },
      { label: "素材库", tab: "assets" },
    ]
  : [
      { label: "推广链接", tab: "links" },
      { label: "投放建议", tab: "ads", primary: true },
      { label: "经营复盘", tab: "reviews" },
    ])

async function loadProducts(): Promise<void> {
  loading.value = true
  try {
    const result = await getProducts({
      page: page.value,
      page_size: pageSize.value,
      q: query.value.trim() || undefined,
    })
    products.value = result.items
    total.value = result.total
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "商品工作区加载失败"))
  } finally {
    loading.value = false
  }
}

function search(): void {
  page.value = 1
  void loadProducts()
}

function resetSearch(): void {
  query.value = ""
  page.value = 1
  void loadProducts()
}

function changePage(value: number): void {
  page.value = value
  void loadProducts()
}

function changePageSize(value: number): void {
  pageSize.value = value
  page.value = 1
  void loadProducts()
}

function openWorkspace(productId: number, tab = actions.value[0].tab): void {
  void router.push({
    name: "product-detail",
    params: { productId, tab },
  })
}

watch(() => route.name, () => {
  page.value = 1
  query.value = ""
  void loadProducts()
})

onMounted(loadProducts)
</script>

<template>
  <div>
    <PageHeader
      :eyebrow="pageCopy.eyebrow"
      :title="pageCopy.title"
      :description="pageCopy.description"
    />

    <section class="flow-strip">
      <div v-for="(action, index) in actions" :key="action.tab">
        <span>{{ String(index + 1).padStart(2, '0') }}</span>
        <strong>{{ action.label }}</strong>
      </div>
    </section>

    <DataTableShell
      :loading="loading"
      :total="total"
      :page="page"
      :page-size="pageSize"
      empty-text="还没有可进入工作区的商品"
      @update:page="changePage"
      @update:page-size="changePageSize"
    >
      <template #toolbar>
        <div class="toolbar">
          <el-input
            v-model="query"
            clearable
            placeholder="搜索商品名称或分类"
            :prefix-icon="Search"
            @keyup.enter="search"
            @clear="search"
          />
          <el-button type="primary" plain :icon="Search" @click="search">查询</el-button>
          <el-button :icon="Refresh" @click="resetSearch">重置</el-button>
        </div>
      </template>

      <el-table
        v-if="products.length"
        :data="products"
        table-layout="fixed"
        @row-click="(row: Product) => openWorkspace(row.id)"
      >
        <el-table-column label="商品" min-width="260">
          <template #default="scope">
            <div class="product-cell">
              <el-image v-if="scope.row.images[0]" :src="scope.row.images[0]" fit="cover" />
              <span v-else>商</span>
              <div>
                <strong>{{ scope.row.name }}</strong>
                <small>{{ scope.row.category || '未分类' }} · {{ scope.row.store_name }}</small>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="平台" width="110">
          <template #default="scope">{{ platformLabels[scope.row.platform as StorePlatform] }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope">
            <el-tag
              :type="scope.row.status === 'active' ? 'success' : scope.row.status === 'draft' ? 'warning' : 'info'"
              effect="plain"
            >
              {{ productStatusLabels[scope.row.status as ProductStatus] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="isTaskWorkspace ? '最近诊断' : '最近复盘'" min-width="170">
          <template #default="scope">
            <span class="muted">
              {{ isTaskWorkspace ? formatDate(scope.row.last_diagnosis_at, '尚未诊断') : formatDate(scope.row.last_review_at, '尚未复盘') }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="进入工作区" min-width="300" fixed="right">
          <template #default="scope">
            <div class="row-actions">
              <el-button
                v-for="action in actions"
                :key="action.tab"
                :type="action.primary ? 'primary' : undefined"
                :plain="!action.primary"
                size="small"
                @click.stop="openWorkspace(scope.row.id, action.tab)"
              >
                {{ action.label }}
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </DataTableShell>
  </div>
</template>

<style scoped>
.flow-strip {
  display: flex;
  gap: 10px;
  margin: -8px 0 22px;
}
.flow-strip div {
  display: flex;
  gap: 9px;
  align-items: center;
  padding: 9px 13px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: rgb(255 255 255 / 55%);
}
.flow-strip span { color: var(--color-accent); font-size: 10px; font-weight: 800; }
.flow-strip strong { color: var(--color-ink); font-size: 12px; }
.toolbar { display: grid; grid-template-columns: minmax(260px, 1fr) auto auto; gap: 10px; }
.product-cell { display: flex; gap: 12px; align-items: center; cursor: pointer; }
.product-cell > span,
.product-cell :deep(.el-image) {
  display: grid;
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 9px;
  background: #e8ece7;
  color: #607068;
  font-weight: 800;
}
.product-cell div { display: flex; overflow: hidden; flex-direction: column; }
.product-cell strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.product-cell small,
.muted { margin-top: 3px; color: var(--color-muted); font-size: 12px; }
.row-actions { display: flex; flex-wrap: wrap; gap: 6px; }
:deep(.el-table__row) { cursor: pointer; }
@media (max-width: 720px) {
  .flow-strip { overflow-x: auto; }
  .flow-strip div { flex: 0 0 auto; }
  .toolbar { grid-template-columns: 1fr; }
}
</style>
