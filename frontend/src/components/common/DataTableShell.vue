<script setup lang="ts">
defineProps<{
  loading?: boolean
  total: number
  page: number
  pageSize: number
  emptyText?: string
}>()

const emit = defineEmits<{
  "update:page": [value: number]
  "update:page-size": [value: number]
}>()
</script>

<template>
  <section class="table-shell" v-loading="loading">
    <div v-if="$slots.toolbar" class="table-toolbar"><slot name="toolbar" /></div>
    <div class="table-content">
      <slot />
      <el-empty v-if="total === 0 && !loading" :description="emptyText || '暂无数据'" :image-size="72" />
    </div>
    <footer v-if="total > 0" class="table-footer">
      <span>共 {{ total }} 条记录</span>
      <el-pagination
        background
        layout="sizes, prev, pager, next"
        :current-page="page"
        :page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="total"
        @update:current-page="emit('update:page', $event)"
        @update:page-size="emit('update:page-size', $event)"
      />
    </footer>
  </section>
</template>

<style scoped>
.table-shell {
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  box-shadow: var(--shadow-soft);
}
.table-toolbar {
  padding: 18px 20px;
  border-bottom: 1px solid var(--color-border);
}
.table-content {
  min-height: 220px;
}
.table-content :deep(.el-empty) {
  padding: 46px 0;
}
.table-footer {
  display: flex;
  gap: 20px;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-top: 1px solid var(--color-border);
  color: var(--color-muted);
  font-size: 13px;
}
@media (max-width: 700px) {
  .table-footer {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>

