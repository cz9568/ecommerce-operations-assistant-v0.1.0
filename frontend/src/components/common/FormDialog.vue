<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue: boolean
    title: string
    loading?: boolean
    confirmText?: string
    width?: string
  }>(),
  { confirmText: "保存", width: "560px" },
)

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  confirm: []
}>()
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    :width="width"
    destroy-on-close
    align-center
    @update:model-value="emit('update:modelValue', $event)"
  >
    <slot />
    <template #footer>
      <el-button :disabled="loading" @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="emit('confirm')">
        {{ confirmText }}
      </el-button>
    </template>
  </el-dialog>
</template>

