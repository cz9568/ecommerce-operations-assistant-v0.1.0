import { createRouter, createWebHistory } from "vue-router"

import AppLayout from "../layouts/AppLayout.vue"
import { pinia } from "../stores"
import { useAuthStore } from "../stores/auth"
import type { Permission } from "../types/domain"

declare module "vue-router" {
  interface RouteMeta {
    title?: string
    requiresAuth?: boolean
    guestOnly?: boolean
    permission?: Permission
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("../views/LoginView.vue"),
      meta: { title: "登录", guestOnly: true },
    },
    {
      path: "/",
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        { path: "", redirect: "/dashboard" },
        {
          path: "dashboard",
          name: "dashboard",
          component: () => import("../views/DashboardView.vue"),
          meta: { title: "工作台", requiresAuth: true },
        },
        {
          path: "users",
          name: "users",
          component: () => import("../views/UserManagementView.vue"),
          meta: { title: "用户管理", requiresAuth: true, permission: "user.manage" },
        },
        {
          path: "stores",
          name: "stores",
          component: () => import("../views/StoreListView.vue"),
          meta: { title: "店铺管理", requiresAuth: true },
        },
        {
          path: "stores/:storeId(\\d+)",
          name: "store-detail",
          component: () => import("../views/StoreDetailView.vue"),
          meta: { title: "店铺详情", requiresAuth: true },
        },
        {
          path: "products",
          name: "products",
          component: () => import("../views/ProductListView.vue"),
          meta: { title: "商品运营", requiresAuth: true },
        },
        {
          path: "products/:productId(\\d+)/:tab?",
          name: "product-detail",
          component: () => import("../views/ProductDetailView.vue"),
          meta: { title: "商品详情", requiresAuth: true },
        },
        {
          path: "imports",
          name: "imports",
          component: () => import("../views/ImportCenterView.vue"),
          meta: { title: "导入中心", requiresAuth: true, permission: "product.write" },
        },
        {
          path: "task-assets",
          name: "task-assets",
          component: () => import("../views/OperationsWorkspaceView.vue"),
          meta: { title: "任务与素材", requiresAuth: true },
        },
        {
          path: "marketing-review",
          name: "marketing-review",
          component: () => import("../views/OperationsWorkspaceView.vue"),
          meta: { title: "投放与复盘", requiresAuth: true },
        },
        {
          path: "settings",
          name: "settings",
          component: () => import("../views/SettingsView.vue"),
          meta: { title: "系统设置", requiresAuth: true, permission: "settings.manage" },
        },
        {
          path: "forbidden",
          name: "forbidden",
          component: () => import("../views/ForbiddenView.vue"),
          meta: { title: "无权访问", requiresAuth: true },
        },
      ],
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("../views/NotFoundView.vue"),
      meta: { title: "页面不存在" },
    },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore(pinia)
  await authStore.restoreSession()

  if (to.meta.guestOnly && authStore.isAuthenticated) return { name: "dashboard" }
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } }
  }
  if (to.meta.permission && !authStore.can(to.meta.permission)) return { name: "forbidden" }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 电商运营助手` : "电商运营助手"
})

export default router
