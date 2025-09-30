<template>
  <UModal
    :open="open"
    :close="{ onClick: () => emit('close', false) }"
    :title="title"
    :ui="{ footer: 'justify-end' }"
  >
    <template #body>
      <div class="space-y-4">
        <div class="flex items-center gap-3">
          <UIcon 
            :name="iconName" 
            :class="iconClass"
          />
          <div>
            <p class="text-gray-900 dark:text-gray-100">
              {{ message }}
            </p>
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <div class="flex gap-3">
        <UButton 
          :label="cancelText" 
          color="neutral" 
          variant="outline" 
          @click="emit('close', false)"
        />
        <UButton 
          :label="confirmText" 
          :color="buttonColor"
          @click="emit('close', true)"
        />
      </div>
    </template>
  </UModal>
</template>

<script setup lang="ts">
// Props
interface Props {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  type?: 'warning' | 'error' | 'info' | 'success'
  open?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '确认操作',
  confirmText: '确认',
  cancelText: '取消',
  type: 'warning',
  open: true
})

// Emits
const emit = defineEmits<{
  'close': [confirmed: boolean]
}>()

// 计算属性
const iconName = computed(() => {
  const icons = {
    warning: 'i-heroicons-exclamation-triangle',
    error: 'i-heroicons-x-circle',
    info: 'i-heroicons-information-circle',
    success: 'i-heroicons-check-circle'
  }
  return icons[props.type]
})

const iconClass = computed(() => {
  const classes = {
    warning: 'h-6 w-6 text-orange-500',
    error: 'h-6 w-6 text-red-500',
    info: 'h-6 w-6 text-blue-500',
    success: 'h-6 w-6 text-green-500'
  }
  return classes[props.type]
})

const buttonColor = computed(() => {
  const colors = {
    warning: 'warning' as const,
    error: 'error' as const,
    info: 'info' as const,
    success: 'success' as const
  }
  return colors[props.type]
})
</script> 