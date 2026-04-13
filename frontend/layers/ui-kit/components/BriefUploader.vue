<template>
  <div
    class="p-3 rounded-lg space-y-2 transition-colors"
    :class="isDragging
      ? 'bg-primary-50 dark:bg-primary-900/20 border-2 border-dashed border-primary-400'
      : 'bg-gray-50 dark:bg-gray-800'"
    @dragenter.prevent="handleDragEnter"
    @dragleave="handleDragLeave"
    @dragover.prevent
    @drop.prevent="handleDrop"
  >
    <p
      class="text-xs font-medium"
      :class="isDragging ? 'text-primary-600 dark:text-primary-400' : 'text-gray-500 dark:text-gray-400'"
    >
      {{ isDragging ? '松开以解析文件' : label }}
    </p>
    <div class="flex gap-2">
      <UTextarea
        v-model="pasteText"
        :placeholder="placeholder"
        :rows="2"
        class="flex-1"
        :disabled="loading"
      />
      <div class="flex flex-col gap-1.5">
        <UButton
          size="sm"
          :loading="loading"
          :disabled="!pasteText.trim() || loading"
          icon="i-heroicons-sparkles"
          @click="handleTextSubmit"
        >
          解析
        </UButton>
        <UButton
          size="sm"
          variant="outline"
          :disabled="loading"
          @click="fileInputRef?.click()"
        >
          上传文件
        </UButton>
      </div>
    </div>
    <p class="text-xs text-gray-400">支持 PDF / DOCX / TXT / MD，最大 10 MB，可直接拖入</p>

    <input
      ref="fileInputRef"
      type="file"
      accept=".pdf,.docx,.txt,.md"
      class="hidden"
      @change="handleFileChange"
    >
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = withDefaults(defineProps<{
  loading?: boolean
  label?: string
  placeholder?: string
}>(), {
  loading: false,
  label: 'AI 快速填入（可选）',
  placeholder: '粘贴 Brief 文本，AI 自动提取关键信息...',
})

const emit = defineEmits<{
  textSubmit: [text: string]
  fileSubmit: [file: File]
}>()

const pasteText = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const dragCounter = ref(0)
const isDragging = computed(() => dragCounter.value > 0)

const handleDragEnter = () => { if (!props.loading) dragCounter.value++ }
const handleDragLeave = () => { dragCounter.value = Math.max(0, dragCounter.value - 1) }
const handleDrop = (e: DragEvent) => {
  dragCounter.value = 0
  if (props.loading) return
  const file = e.dataTransfer?.files?.[0]
  if (file) submitFile(file)
}
const handleFileChange = (e: Event) => {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) submitFile(file)
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function handleTextSubmit() {
  const text = pasteText.value.trim()
  if (!text) return
  emit('textSubmit', text)
  pasteText.value = ''
}

function submitFile(file: File) {
  emit('fileSubmit', file)
}
</script>
