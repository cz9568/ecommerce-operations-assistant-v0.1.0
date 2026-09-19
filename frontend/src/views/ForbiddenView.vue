<script setup lang="ts">
import { Lock } from "@element-plus/icons-vue"
import { useRouter } from "vue-router"
const router = useRouter()
</script>
<template>
  <section class="state-page"><div class="state-icon"><Lock /></div><p>403 · PERMISSION DENIED</p><h1>当前角色无权访问</h1><span>如果工作职责发生变化，请联系管理员调整账号角色。</span><el-button type="primary" @click="router.push('/dashboard')">返回工作台</el-button></section>
</template>
<style scoped>
.state-page { display: flex; min-height: 65vh; align-items: center; flex-direction: column; justify-content: center; text-align: center; }
.state-icon { width: 58px; color: var(--color-accent); }
.state-page p { margin: 24px 0 8px; color: var(--color-accent); font-size: 11px; font-weight: 800; letter-spacing: .16em; }
.state-page h1 { margin: 0; font-family: var(--font-display); font-size: 42px; font-weight: 500; }
.state-page span { margin: 14px 0 28px; color: var(--color-muted); }
</style>

