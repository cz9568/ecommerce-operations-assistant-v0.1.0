<script setup lang="ts">
import { useRouter } from "vue-router"
const router = useRouter()
</script>
<template>
  <main class="not-found"><p>404</p><h1>页面走丢了</h1><span>你访问的地址不存在，或者页面已经移动。</span><el-button type="primary" @click="router.push('/dashboard')">返回工作台</el-button></main>
</template>
<style scoped>
.not-found { display: flex; min-height: 100vh; align-items: center; flex-direction: column; justify-content: center; background: var(--color-bg); text-align: center; }
.not-found p { margin: 0; color: var(--color-accent); font-family: var(--font-display); font-size: 100px; line-height: 1; }
.not-found h1 { margin: 14px 0 8px; font-family: var(--font-display); font-size: 38px; font-weight: 500; }
.not-found span { margin-bottom: 28px; color: var(--color-muted); }
</style>

