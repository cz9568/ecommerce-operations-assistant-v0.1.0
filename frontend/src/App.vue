<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import axios from "axios"

type ServiceState = "checking" | "online" | "offline"

const serviceState = ref<ServiceState>("checking")
const statusText = computed(() => {
  const labels: Record<ServiceState, string> = {
    checking: "正在检查服务",
    online: "后端服务正常",
    offline: "后端服务未启动",
  }
  return labels[serviceState.value]
})

onMounted(async () => {
  try {
    await axios.get("/api/v1/health/live", { timeout: 3000 })
    serviceState.value = "online"
  } catch {
    serviceState.value = "offline"
  }
})

const modules = [
  { name: "商品与竞品", text: "建立商品、SKU、库存和竞品档案", step: "01" },
  { name: "诊断与方案", text: "生成可编辑的诊断、主图方案和视频脚本", step: "02" },
  { name: "任务与素材", text: "追踪异步生成任务并审核素材", step: "03" },
  { name: "投放与复盘", text: "确认投放建议并根据经营数据持续优化", step: "04" },
]
</script>

<template>
  <main class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">E-COMMERCE OPERATIONS</p>
        <h1>让每个商品的运营过程<br />有迹可循</h1>
        <p class="intro">
          从商品建档到经营复盘，把分散的运营动作整理成一条清晰、可编辑、可回溯的工作流。
        </p>
        <div class="actions">
          <el-button type="primary" size="large" disabled>进入工作台</el-button>
          <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">查看 API 文档</a>
        </div>
      </div>
      <aside class="status-card">
        <span class="status-dot" :class="serviceState" />
        <div>
          <strong>{{ statusText }}</strong>
          <p>基础工程已就绪，下一阶段将实现登录与权限。</p>
        </div>
      </aside>
    </section>

    <section class="workflow" aria-label="核心工作流">
      <article v-for="item in modules" :key="item.step" class="module-card">
        <span>{{ item.step }}</span>
        <h2>{{ item.name }}</h2>
        <p>{{ item.text }}</p>
      </article>
    </section>
  </main>
</template>

