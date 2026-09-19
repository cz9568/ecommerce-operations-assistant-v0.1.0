<script setup lang="ts">
import {
  ArrowRight,
  DataAnalysis,
  Fold,
  Goods,
  Shop,
  Menu as MenuIcon,
  UploadFilled,
  Setting,
  SwitchButton,
  User,
  UserFilled,
} from "@element-plus/icons-vue"
import { ElMessageBox } from "element-plus"
import { computed, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { useAuthStore } from "../stores/auth"

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const collapsed = ref(false)
const mobileMenuOpen = ref(false)

const roleLabels = { admin: "管理员", operator: "运营人员", viewer: "查看人员" } as const
const currentTitle = computed(() => String(route.meta.title ?? "工作台"))

async function handleLogout(): Promise<void> {
  await ElMessageBox.confirm("退出后需要重新登录，确定继续吗？", "退出登录", {
    confirmButtonText: "退出",
    cancelButtonText: "取消",
    type: "warning",
  })
  await authStore.signOut()
  await router.replace({ name: "login" })
}

function navigate(path: string): void {
  mobileMenuOpen.value = false
  void router.push(path)
}
</script>

<template>
  <div class="app-layout" :class="{ collapsed }">
    <aside class="sidebar">
      <button class="brand" type="button" aria-label="返回工作台" @click="navigate('/dashboard')">
        <span class="brand-mark">曜</span>
        <span v-show="!collapsed" class="brand-copy">
          <strong>电商运营助手</strong>
          <small>OPERATIONS STUDIO</small>
        </span>
      </button>

      <nav class="nav-list" aria-label="主导航">
        <button
          class="nav-item"
          :class="{ active: route.path === '/dashboard' }"
          type="button"
          @click="navigate('/dashboard')"
        >
          <el-icon><DataAnalysis /></el-icon>
          <span v-show="!collapsed">工作台</span>
        </button>
        <div v-show="!collapsed" class="nav-section">运营流程</div>
        <button class="nav-item" :class="{ active: route.path.startsWith('/stores') }" type="button" @click="navigate('/stores')">
          <el-icon><Shop /></el-icon>
          <span v-show="!collapsed">店铺管理</span>
        </button>
        <button class="nav-item" :class="{ active: route.path.startsWith('/products') }" type="button" @click="navigate('/products')">
          <el-icon><Goods /></el-icon>
          <span v-show="!collapsed">商品运营</span>
        </button>
        <button v-if="authStore.can('product.write')" class="nav-item" :class="{ active: route.path === '/imports' }" type="button" @click="navigate('/imports')">
          <el-icon><UploadFilled /></el-icon>
          <span v-show="!collapsed">导入中心</span>
        </button>
        <button
          class="nav-item"
          :class="{ active: route.path === '/task-assets' }"
          type="button"
          @click="navigate('/task-assets')"
        >
          <el-icon><MenuIcon /></el-icon>
          <span v-show="!collapsed">任务与素材</span>
        </button>
        <button
          class="nav-item"
          :class="{ active: route.path === '/marketing-review' }"
          type="button"
          @click="navigate('/marketing-review')"
        >
          <el-icon><ArrowRight /></el-icon>
          <span v-show="!collapsed">投放与复盘</span>
        </button>
        <div v-show="!collapsed && authStore.can('user.manage')" class="nav-section">系统</div>
        <button
          v-if="authStore.can('user.manage')"
          class="nav-item"
          :class="{ active: route.path === '/users' }"
          type="button"
          @click="navigate('/users')"
        >
          <el-icon><User /></el-icon>
          <span v-show="!collapsed">用户管理</span>
        </button>
        <button v-if="authStore.can('settings.manage')" class="nav-item" :class="{ active: route.path === '/settings' }" type="button" @click="navigate('/settings')">
          <el-icon><Setting /></el-icon>
          <span v-show="!collapsed">系统设置</span>
        </button>
      </nav>

      <button class="collapse-button" type="button" @click="collapsed = !collapsed">
        <el-icon><Fold /></el-icon>
        <span v-show="!collapsed">收起导航</span>
      </button>
    </aside>

    <el-drawer v-model="mobileMenuOpen" direction="ltr" size="280px" :with-header="false">
      <div class="mobile-menu">
        <div class="mobile-brand">电商运营助手</div>
        <button type="button" @click="navigate('/dashboard')">工作台</button>
        <button type="button" @click="navigate('/stores')">店铺管理</button>
        <button type="button" @click="navigate('/products')">商品运营</button>
        <button v-if="authStore.can('product.write')" type="button" @click="navigate('/imports')">导入中心</button>
        <button type="button" @click="navigate('/task-assets')">任务与素材</button>
        <button type="button" @click="navigate('/marketing-review')">投放与复盘</button>
        <button v-if="authStore.can('user.manage')" type="button" @click="navigate('/users')">
          用户管理
        </button>
        <button v-if="authStore.can('settings.manage')" type="button" @click="navigate('/settings')">系统设置</button>
      </div>
    </el-drawer>

    <section class="main-area">
      <header class="topbar">
        <div class="topbar-title">
          <el-button class="mobile-trigger" text :icon="MenuIcon" @click="mobileMenuOpen = true" />
          <span>{{ currentTitle }}</span>
        </div>
        <el-dropdown trigger="click">
          <button class="user-menu" type="button">
            <el-avatar :size="36"><el-icon><UserFilled /></el-icon></el-avatar>
            <span class="user-copy">
              <strong>{{ authStore.user?.display_name }}</strong>
              <small>{{ authStore.user ? roleLabels[authStore.user.role] : '' }}</small>
            </span>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item :icon="SwitchButton" @click="handleLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </header>

      <main class="content-area"><router-view /></main>
    </section>
  </div>
</template>

<style scoped>
.app-layout { min-height: 100vh; }
.sidebar {
  position: fixed; z-index: 20; inset: 0 auto 0 0; display: flex; width: 252px;
  flex-direction: column; padding: 22px 16px 16px; border-right: 1px solid rgb(255 255 255 / 8%);
  background: #17221e; color: #eef2ed; transition: width 0.25s ease;
}
.collapsed .sidebar { width: 82px; }
.brand {
  display: flex; gap: 12px; align-items: center; min-height: 46px; padding: 0 8px;
  border: 0; background: none; color: inherit; cursor: pointer; text-align: left;
}
.brand-mark {
  display: grid; width: 38px; height: 38px; flex: 0 0 auto; place-items: center;
  border-radius: 10px; background: var(--color-accent); color: white;
  font-family: var(--font-display); font-size: 20px;
}
.brand-copy { display: flex; min-width: 0; flex-direction: column; }
.brand-copy strong { font-size: 15px; letter-spacing: 0.04em; }
.brand-copy small { margin-top: 3px; color: #8fa098; font-size: 9px; letter-spacing: 0.14em; }
.nav-list { display: flex; flex: 1; flex-direction: column; gap: 6px; margin-top: 34px; }
.nav-section { margin: 22px 12px 6px; color: #7c8c84; font-size: 10px; font-weight: 700; letter-spacing: 0.16em; }
.nav-item, .collapse-button {
  display: flex; gap: 13px; align-items: center; min-height: 44px; padding: 0 13px;
  border: 0; border-radius: 9px; background: transparent; color: #aebbb4;
  cursor: pointer; font-size: 14px; text-align: left; transition: 0.18s ease;
}
.nav-item .el-icon, .collapse-button .el-icon { flex: 0 0 auto; font-size: 18px; }
.nav-item:hover:not(:disabled), .nav-item.active { background: rgb(255 255 255 / 9%); color: white; }
.nav-item.active { box-shadow: inset 3px 0 var(--color-accent); }
.nav-item small { margin-left: auto; color: #65766d; font-size: 10px; }
.collapse-button { width: 100%; border-top: 1px solid rgb(255 255 255 / 8%); border-radius: 0; }
.main-area { min-height: 100vh; margin-left: 252px; transition: margin-left 0.25s ease; }
.collapsed .main-area { margin-left: 82px; }
.topbar {
  position: sticky; z-index: 10; top: 0; display: flex; height: 70px; align-items: center;
  justify-content: space-between; padding: 0 32px; border-bottom: 1px solid var(--color-border);
  background: rgb(247 245 239 / 88%); backdrop-filter: blur(16px);
}
.topbar-title { display: flex; align-items: center; color: var(--color-ink); font-size: 14px; font-weight: 700; }
.mobile-trigger { display: none; }
.user-menu {
  display: flex; gap: 10px; align-items: center; padding: 6px 8px; border: 0;
  border-radius: 10px; background: transparent; cursor: pointer;
}
.user-menu:hover { background: rgb(23 34 30 / 5%); }
.user-copy { display: flex; flex-direction: column; text-align: left; }
.user-copy strong { color: var(--color-ink); font-size: 13px; }
.user-copy small { margin-top: 2px; color: var(--color-muted); font-size: 11px; }
.content-area { width: min(1280px, 100%); margin: 0 auto; padding: 36px 38px 64px; }
.mobile-menu { display: flex; flex-direction: column; gap: 8px; }
.mobile-brand { margin-bottom: 20px; font-family: var(--font-display); font-size: 22px; }
.mobile-menu button { padding: 12px; border: 0; border-radius: 8px; background: #f2f3ef; color: var(--color-ink); text-align: left; }
@media (max-width: 900px) {
  .sidebar { display: none; }
  .main-area, .collapsed .main-area { margin-left: 0; }
  .mobile-trigger { display: inline-flex; margin-right: 6px; }
  .content-area { padding: 28px 20px 52px; }
}
@media (max-width: 560px) {
  .topbar { padding: 0 14px; }
  .user-copy { display: none; }
}
</style>
