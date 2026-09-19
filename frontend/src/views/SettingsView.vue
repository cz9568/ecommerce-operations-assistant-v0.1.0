<script setup lang="ts">
import { Refresh, Setting, User } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import { computed, onMounted, reactive, ref } from "vue"
import { useRouter } from "vue-router"

import { getApiErrorMessage } from "../api/http"
import { getSettings, saveSettings } from "../api/settings"
import PageHeader from "../components/common/PageHeader.vue"
import type { SettingApplyMode, SettingGroup, SettingItem, SettingsData } from "../types/domain"

const router = useRouter(); const active = ref<SettingGroup | "users">("model")
const data = ref<SettingsData | null>(null); const form = reactive<Record<string, string | number>>({})
const loading = ref(false); const saving = ref(false)
const modeLabels: Record<SettingApplyMode, string> = { immediate: "立即用于新任务", new_requests: "新请求立即生效", worker_restart: "重启 Worker 生效", service_restart: "重启后端生效" }
const currentItems = computed(() => active.value === "users" ? [] : data.value?.groups[active.value] || [])
function hydrate(result: SettingsData): void { data.value = result; for (const items of Object.values(result.groups)) for (const item of items) form[item.key] = item.sensitive ? "" : (item.value as string | number) }
async function load(): Promise<void> { loading.value = true; try { hydrate(await getSettings()) } catch (error) { ElMessage.error(getApiErrorMessage(error, "系统设置加载失败")) } finally { loading.value = false } }
function options(item: SettingItem): Array<{ label: string; value: string | number }> {
  if (item.key === "generation_provider") return [{ label: "Mock（开发）", value: "mock" }, { label: "DashScope", value: "dashscope" }]
  if (item.key === "video_duration_seconds") return [{ label: "5 秒", value: 5 }, { label: "10 秒", value: 10 }]
  if (item.key === "video_size") return ["1280*720", "720*1280", "1920*1080", "1080*1920"].map((value) => ({ label: value, value }))
  return []
}
async function save(): Promise<void> {
  if (active.value === "users") return
  const values: Record<string, unknown> = {}
  for (const item of currentItems.value) if (!item.sensitive || form[item.key]) values[item.key] = form[item.key]
  saving.value = true
  try { hydrate(await saveSettings(active.value, values)); ElMessage.success("设置已保存，请留意每项右侧的生效方式") }
  catch (error) { ElMessage.error(getApiErrorMessage(error, "设置保存失败")) }
  finally { saving.value = false }
}
onMounted(() => void load())
</script>

<template>
  <section class="settings-page">
    <PageHeader eyebrow="SYSTEM CONTROL" title="系统设置" description="集中管理模型、系统和任务队列参数；敏感值加密保存且永不回显。"><template #actions><el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button></template></PageHeader>
    <div class="settings-shell" v-loading="loading"><aside><button v-for="item in [{key:'model',label:'模型配置'},{key:'users',label:'用户与权限'},{key:'system',label:'系统参数'},{key:'queue',label:'任务队列'}]" :key="item.key" :class="{active:active===item.key}" @click="active=item.key as SettingGroup | 'users'">{{ item.label }}</button></aside><main>
      <template v-if="active === 'users'"><div class="user-entry"><el-icon><User /></el-icon><div><h2>用户与权限</h2><p>用户创建、角色分配、启停用和最后管理员保护集中在用户管理页面。</p></div><el-button type="primary" @click="router.push('/users')">进入用户管理</el-button></div></template>
      <template v-else><header><div><p>{{ active.toUpperCase() }} SETTINGS</p><h2>{{ active === 'model' ? '模型配置' : active === 'system' ? '系统参数' : '任务队列' }}</h2></div><el-button type="primary" :icon="Setting" :loading="saving" @click="save">保存本组设置</el-button></header><el-alert title="数据库连接、JWT 密钥和存储根目录属于启动级安全配置，不允许在网页中修改。" type="info" show-icon :closable="false" /><div class="setting-list"><article v-for="item in currentItems" :key="item.key"><div class="copy"><span><b>{{ item.label }}</b><el-tag size="small" :type="item.source === 'database' ? 'success' : 'info'">{{ item.source === 'database' ? '已覆盖' : '环境默认' }}</el-tag></span><p>{{ item.description }}</p><code>{{ item.key }}</code></div><div class="control"><el-select v-if="options(item).length" v-model="form[item.key]"><el-option v-for="option in options(item)" :key="option.value" :label="option.label" :value="option.value" /></el-select><el-input-number v-else-if="item.value_type === 'integer'" v-model="form[item.key] as number" :min="0" controls-position="right" /><el-input v-else v-model="form[item.key] as string" :type="item.sensitive ? 'password' : 'text'" :show-password="item.sensitive" :placeholder="item.sensitive && item.configured ? '已配置；留空保持不变' : '请输入配置值'" /><small>{{ modeLabels[item.apply_mode] }}</small></div></article></div></template>
    </main></div>
  </section>
</template>

<style scoped>
.settings-page{display:flex;flex-direction:column;gap:18px}.settings-shell{display:grid;min-height:640px;grid-template-columns:190px minmax(0,1fr);overflow:hidden;border:1px solid var(--color-border);border-radius:14px;background:var(--color-surface);box-shadow:var(--shadow-soft)}aside{display:flex;flex-direction:column;gap:5px;padding:15px;border-right:1px solid var(--color-border);background:#f4f1e9}aside button{padding:12px;border:0;border-radius:8px;background:none;color:var(--color-muted);text-align:left;cursor:pointer}aside button.active,aside button:hover{background:#fff;color:var(--color-ink);font-weight:700}main{padding:24px}main>header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px}main>header p{margin:0;color:var(--color-accent);font-size:10px;font-weight:800;letter-spacing:.15em}main h2{margin:6px 0;font-family:var(--font-display);font-size:27px;font-weight:500}.setting-list{margin-top:18px}.setting-list article{display:grid;grid-template-columns:minmax(260px,1fr) minmax(260px,420px);gap:25px;padding:18px 0;border-bottom:1px solid var(--color-border)}.copy span{display:flex;align-items:center;gap:8px}.copy p{margin:7px 0;color:var(--color-muted);font-size:12px;line-height:1.6}.copy code{color:#8a8176;font-size:10px}.control{display:flex;align-items:stretch;flex-direction:column;gap:6px}.control :deep(.el-select),.control :deep(.el-input-number){width:100%}.control small{color:var(--color-muted);font-size:10px;text-align:right}.user-entry{display:flex;min-height:400px;align-items:center;justify-content:center;flex-direction:column;text-align:center}.user-entry .el-icon{font-size:42px;color:var(--color-accent)}.user-entry p{max-width:520px;color:var(--color-muted);line-height:1.7}.user-entry .el-button{margin-top:15px}@media(max-width:760px){.settings-shell{grid-template-columns:1fr}aside{overflow-x:auto;flex-direction:row;border-right:0;border-bottom:1px solid var(--color-border)}aside button{min-width:120px}.setting-list article{grid-template-columns:1fr}}
</style>
