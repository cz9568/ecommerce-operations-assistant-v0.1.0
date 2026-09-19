<script setup lang="ts">
import { Plus, Refresh, Search } from "@element-plus/icons-vue"
import { ElMessage } from "element-plus"
import type { FormInstance, FormItemRule, FormRules } from "element-plus"
import { computed, onMounted, reactive, ref } from "vue"

import { createUser, getUsers, updateUser } from "../api/users"
import type { CreateUserPayload, UpdateUserPayload } from "../api/users"
import { getApiErrorMessage } from "../api/http"
import DataTableShell from "../components/common/DataTableShell.vue"
import FormDialog from "../components/common/FormDialog.vue"
import PageHeader from "../components/common/PageHeader.vue"
import type { User, UserRole, UserStatus } from "../types/domain"

interface UserFormModel {
  username: string
  display_name: string
  password: string
  role: UserRole
  status: UserStatus
}

const users = ref<User[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const query = ref("")
const roleFilter = ref<UserRole | "">("")
const statusFilter = ref<UserStatus | "">("")
const dialogVisible = ref(false)
const saving = ref(false)
const editingUser = ref<User | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<UserFormModel>(emptyForm())

const roleLabels: Record<UserRole, string> = { admin: "管理员", operator: "运营人员", viewer: "查看人员" }
const roleTagTypes: Record<UserRole, "danger" | "warning" | "info"> = { admin: "danger", operator: "warning", viewer: "info" }
const dialogTitle = computed(() => (editingUser.value ? `编辑用户 · ${editingUser.value.username}` : "创建用户"))

const passwordValidator: FormItemRule["validator"] = (_rule, value: string, callback) => {
  if (!editingUser.value && !value) return callback(new Error("请输入初始密码"))
  if (!value && editingUser.value) return callback()
  if (value.length < 12 || !/[A-Z]/.test(value) || !/[a-z]/.test(value) || !/\d/.test(value)) {
    return callback(new Error("至少 12 位，并包含大小写字母和数字"))
  }
  callback()
}

const rules = computed<FormRules<UserFormModel>>(() => ({
  username: [
    { required: true, message: "请输入用户名", trigger: "blur" },
    { pattern: /^[A-Za-z0-9_.-]+$/, message: "仅支持字母、数字、点、横线和下划线", trigger: "blur" },
  ],
  display_name: [{ required: true, message: "请输入显示名称", trigger: "blur" }],
  password: [{ validator: passwordValidator, trigger: "blur" }],
  role: [{ required: true, message: "请选择角色", trigger: "change" }],
  status: [{ required: true, message: "请选择状态", trigger: "change" }],
}))

function emptyForm(): UserFormModel {
  return { username: "", display_name: "", password: "", role: "viewer", status: "active" }
}

async function loadUsers(): Promise<void> {
  loading.value = true
  try {
    const result = await getUsers({
      page: page.value,
      page_size: pageSize.value,
      q: query.value.trim() || undefined,
      role: roleFilter.value || undefined,
      status: statusFilter.value || undefined,
    })
    users.value = result.items
    total.value = result.total
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "用户列表加载失败"))
  } finally {
    loading.value = false
  }
}

function resetForm(model: UserFormModel): void {
  Object.assign(form, model)
  formRef.value?.clearValidate()
}

function openCreate(): void {
  editingUser.value = null
  resetForm(emptyForm())
  dialogVisible.value = true
}

function openEdit(user: User): void {
  editingUser.value = user
  resetForm({
    username: user.username,
    display_name: user.display_name,
    password: "",
    role: user.role,
    status: user.status,
  })
  dialogVisible.value = true
}

async function submitUser(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (editingUser.value) {
      const payload: UpdateUserPayload = {
        display_name: form.display_name,
        role: form.role,
        status: form.status,
      }
      if (form.password) payload.password = form.password
      await updateUser(editingUser.value.id, payload)
      ElMessage.success("用户信息已更新")
    } else {
      const payload: CreateUserPayload = {
        username: form.username,
        display_name: form.display_name,
        password: form.password,
        role: form.role,
        status: form.status,
      }
      await createUser(payload)
      ElMessage.success("用户创建成功")
    }
    dialogVisible.value = false
    await loadUsers()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, "保存失败"))
  } finally {
    saving.value = false
  }
}

function search(): void {
  page.value = 1
  void loadUsers()
}

function resetFilters(): void {
  query.value = ""
  roleFilter.value = ""
  statusFilter.value = ""
  page.value = 1
  void loadUsers()
}

function changePage(value: number): void {
  page.value = value
  void loadUsers()
}

function changePageSize(value: number): void {
  pageSize.value = value
  page.value = 1
  void loadUsers()
}

function formatDate(value: string | null): string {
  if (!value) return "从未登录"
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
}

onMounted(loadUsers)
</script>

<template>
  <div>
    <PageHeader
      eyebrow="ACCESS CONTROL"
      title="用户与角色"
      description="管理工作台成员、角色和启用状态。权限最终由后端校验，停用账号后其现有登录状态会在下次请求时失效。"
    >
      <template #actions>
        <el-button type="primary" :icon="Plus" @click="openCreate">创建用户</el-button>
      </template>
    </PageHeader>

    <DataTableShell
      :loading="loading"
      :total="total"
      :page="page"
      :page-size="pageSize"
      empty-text="还没有符合条件的用户"
      @update:page="changePage"
      @update:page-size="changePageSize"
    >
      <template #toolbar>
        <div class="filters">
          <el-input v-model="query" clearable placeholder="搜索用户名或显示名称" :prefix-icon="Search" @keyup.enter="search" />
          <el-select v-model="roleFilter" clearable placeholder="全部角色">
            <el-option label="管理员" value="admin" /><el-option label="运营人员" value="operator" /><el-option label="查看人员" value="viewer" />
          </el-select>
          <el-select v-model="statusFilter" clearable placeholder="全部状态">
            <el-option label="启用" value="active" /><el-option label="停用" value="inactive" />
          </el-select>
          <el-button type="primary" plain :icon="Search" @click="search">查询</el-button>
          <el-button :icon="Refresh" @click="resetFilters">重置</el-button>
        </div>
      </template>

      <el-table v-if="users.length" :data="users" table-layout="fixed">
        <el-table-column label="用户" min-width="210">
          <template #default="scope">
            <div class="user-cell"><span>{{ scope.row.display_name.slice(0, 1) }}</span><div><strong>{{ scope.row.display_name }}</strong><small>@{{ scope.row.username }}</small></div></div>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="130">
          <template #default="scope"><el-tag :type="roleTagTypes[scope.row.role as UserRole]" effect="light">{{ roleLabels[scope.row.role as UserRole] }}</el-tag></template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="scope"><span class="status-label" :class="scope.row.status"><i />{{ scope.row.status === 'active' ? '启用' : '停用' }}</span></template>
        </el-table-column>
        <el-table-column label="最近登录" min-width="180">
          <template #default="scope"><span class="muted">{{ formatDate(scope.row.last_login_at) }}</span></template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180">
          <template #default="scope"><span class="muted">{{ formatDate(scope.row.created_at) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="scope"><el-button link type="primary" @click="openEdit(scope.row as User)">编辑</el-button></template>
        </el-table-column>
      </el-table>
    </DataTableShell>

    <FormDialog v-model="dialogVisible" :title="dialogTitle" :loading="saving" @confirm="submitUser">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <div class="form-grid">
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" :disabled="Boolean(editingUser)" placeholder="例如 operator01" />
          </el-form-item>
          <el-form-item label="显示名称" prop="display_name">
            <el-input v-model="form.display_name" placeholder="团队成员姓名或昵称" />
          </el-form-item>
        </div>
        <el-form-item :label="editingUser ? '重置密码（选填）' : '初始密码'" prop="password">
          <el-input v-model="form.password" type="password" show-password autocomplete="new-password" placeholder="至少 12 位，包含大小写字母和数字" />
        </el-form-item>
        <div class="form-grid">
          <el-form-item label="角色" prop="role">
            <el-select v-model="form.role" style="width: 100%"><el-option label="管理员" value="admin" /><el-option label="运营人员" value="operator" /><el-option label="查看人员" value="viewer" /></el-select>
          </el-form-item>
          <el-form-item label="状态" prop="status">
            <el-radio-group v-model="form.status"><el-radio-button value="active">启用</el-radio-button><el-radio-button value="inactive">停用</el-radio-button></el-radio-group>
          </el-form-item>
        </div>
        <div class="role-note"><strong>权限说明</strong><p>管理员可管理用户和系统；运营人员可执行运营写操作；查看人员只能浏览数据。</p></div>
      </el-form>
    </FormDialog>
  </div>
</template>

<style scoped>
.filters { display: grid; grid-template-columns: minmax(220px, 1fr) 150px 140px auto auto; gap: 10px; }
.user-cell { display: flex; gap: 12px; align-items: center; }
.user-cell > span { display: grid; width: 36px; height: 36px; flex: 0 0 auto; place-items: center; border-radius: 10px; background: #e9ece7; color: #53625b; font-weight: 800; }
.user-cell div { display: flex; overflow: hidden; flex-direction: column; }
.user-cell strong { overflow: hidden; color: var(--color-ink); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.user-cell small { margin-top: 3px; color: var(--color-muted); }
.status-label { display: inline-flex; gap: 7px; align-items: center; color: var(--color-muted); font-size: 13px; }
.status-label i { width: 7px; height: 7px; border-radius: 50%; background: #aab1ad; }
.status-label.active i { background: #3b9962; }
.muted { color: var(--color-muted); font-size: 13px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.role-note { padding: 14px 16px; border-radius: 9px; background: #f1f3ef; }
.role-note strong { color: var(--color-ink); font-size: 12px; }
.role-note p { margin: 6px 0 0; color: var(--color-muted); font-size: 12px; line-height: 1.6; }
@media (max-width: 900px) { .filters { grid-template-columns: 1fr 1fr; } }
@media (max-width: 560px) { .filters, .form-grid { grid-template-columns: 1fr; } }
</style>
