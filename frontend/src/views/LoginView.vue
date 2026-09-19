<script setup lang="ts">
import { Lock, User } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import type { FormInstance, FormRules } from "element-plus"
import { computed, onMounted, reactive, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorMessage } from "../api/http"
import { useAuthStore } from "../stores/auth"

interface LoginForm {
  username: string
  password: string
}

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const formRef = ref<FormInstance>()
const form = reactive<LoginForm>({ username: "", password: "" })
const rules: FormRules<LoginForm> = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
}

const redirectTarget = computed(() => {
  const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/dashboard"
  return redirect.startsWith("/") && !redirect.startsWith("//") ? redirect : "/dashboard"
})

onMounted(() => {
  if (route.query.reason === "expired") ElMessage.warning("登录状态已过期，请重新登录")
})

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  try {
    await authStore.signIn(form)
    ElMessage.success("欢迎回来")
    await router.replace(redirectTarget.value)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "登录失败"))
  }
}
</script>

<template>
  <main class="login-page">
    <section class="story-panel">
      <div class="story-content">
        <p class="story-kicker">OPERATIONS, IN ONE FLOW</p>
        <h1>让好商品<br />被更多人看见</h1>
        <p>从洞察、创意到投放复盘，将每次运营判断沉淀为下一轮增长的依据。</p>
      </div>
      <div class="story-steps" aria-label="业务闭环">
        <span>建档</span><i /><span>诊断</span><i /><span>创意</span><i /><span>投放</span><i /><span>复盘</span>
      </div>
    </section>

    <section class="login-panel">
      <div class="login-card">
        <div class="login-brand"><span>曜</span> 电商运营助手</div>
        <p class="login-eyebrow">WELCOME BACK</p>
        <h2>登录运营工作台</h2>
        <p class="login-hint">使用管理员创建的账号进入系统</p>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" :prefix-icon="User" size="large" autocomplete="username" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              :prefix-icon="Lock"
              size="large"
              type="password"
              show-password
              autocomplete="current-password"
              @keyup.enter="submit"
            />
          </el-form-item>
          <el-button class="login-button" type="primary" size="large" :loading="authStore.loading" @click="submit">
            进入工作台
          </el-button>
        </el-form>
        <p class="security-note">账号凭证仅用于当前系统登录，不会保存平台密码或 Cookie。</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page { display: grid; min-height: 100vh; grid-template-columns: minmax(0, 1.2fr) minmax(440px, 0.8fr); }
.story-panel {
  position: relative; display: flex; overflow: hidden; flex-direction: column; justify-content: space-between;
  padding: clamp(46px, 7vw, 94px); background: #17221e; color: white;
}
.story-panel::before {
  position: absolute; width: 620px; height: 620px; border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 50%; content: ""; right: -220px; top: -220px; box-shadow: 0 0 0 100px rgb(255 255 255 / 2%), 0 0 0 200px rgb(255 255 255 / 2%);
}
.story-content { position: relative; z-index: 1; max-width: 700px; }
.story-kicker { margin: 0 0 36px; color: #e7784d; font-size: 11px; font-weight: 800; letter-spacing: 0.22em; }
.story-content h1 { margin: 0; font-family: var(--font-display); font-size: clamp(58px, 7.8vw, 110px); font-weight: 500; letter-spacing: -0.055em; line-height: 0.98; }
.story-content > p:last-child { max-width: 560px; margin: 38px 0 0; color: #aebbb4; font-size: 17px; line-height: 1.9; }
.story-steps { position: relative; z-index: 1; display: flex; align-items: center; color: #d5ddd8; font-size: 12px; letter-spacing: 0.08em; }
.story-steps i { width: clamp(18px, 4vw, 62px); height: 1px; margin: 0 12px; background: #53625b; }
.login-panel { display: grid; place-items: center; padding: 36px; background: #f5f2e9; }
.login-card { width: min(420px, 100%); }
.login-brand { display: flex; align-items: center; margin-bottom: 76px; color: var(--color-ink); font-weight: 800; }
.login-brand span { display: grid; width: 34px; height: 34px; margin-right: 10px; place-items: center; border-radius: 9px; background: var(--color-accent); color: white; font-family: var(--font-display); }
.login-eyebrow { margin: 0 0 12px; color: var(--color-accent); font-size: 10px; font-weight: 800; letter-spacing: 0.2em; }
h2 { margin: 0; color: var(--color-ink); font-family: var(--font-display); font-size: 38px; font-weight: 500; }
.login-hint { margin: 12px 0 32px; color: var(--color-muted); }
.login-button { width: 100%; margin-top: 8px; }
.security-note { margin: 24px 0 0; color: #929992; font-size: 12px; line-height: 1.7; }
@media (max-width: 920px) {
  .login-page { grid-template-columns: 1fr; }
  .story-panel { min-height: 300px; padding: 42px 28px; }
  .story-content h1 { font-size: 54px; }
  .story-content > p:last-child, .story-steps { display: none; }
  .login-panel { padding: 48px 24px; }
  .login-brand { margin-bottom: 44px; }
}
</style>

