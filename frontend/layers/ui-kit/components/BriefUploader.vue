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

    <div
      v-if="selectedFile"
      class="flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 text-sm"
    >
      <UIcon name="i-heroicons-document-text" class="w-4 h-4 text-primary-500 flex-shrink-0" />
      <span class="font-medium text-gray-800 dark:text-gray-200 truncate">{{ selectedFile.name }}</span>
      <span class="text-xs text-gray-500 flex-shrink-0">{{ formatSize(selectedFile.size) }}</span>
      <span v-if="loading" class="text-xs text-primary-600 dark:text-primary-400 flex-shrink-0">解析中...</span>
      <div class="ml-auto flex items-center gap-1 flex-shrink-0">
        <UButton
          icon="i-heroicons-arrow-path"
          variant="ghost"
          color="neutral"
          size="xs"
          :disabled="loading"
          @click="handleReparse"
        />
        <UButton
          icon="i-heroicons-x-mark"
          variant="ghost"
          color="neutral"
          size="xs"
          :disabled="loading"
          @click="handleRemoveFile"
        />
      </div>
    </div>

    <div class="flex gap-2">
      <UTextarea
        v-model="pasteText"
        :placeholder="placeholder"
        :rows="2"
        autoresize
        class="flex-1"
        :disabled="loading || !!selectedFile"
      />
      <div class="flex flex-col gap-1.5">
        <UButton
          size="sm"
          :loading="loading && !selectedFile"
          :disabled="!pasteText.trim() || loading || !!selectedFile"
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
          {{ selectedFile ? '换文件' : '上传文件' }}
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
  label: '快速填入（可选）',
  placeholder: '粘贴 Brief 文本，AI 自动提取关键信息...',
})

const emit = defineEmits<{
  textSubmit: [text: string]
  fileSubmit: [file: File]
  clear: []
  validationError: [message: string]
}>()

const ALLOWED_EXT = new Set(['pdf', 'docx', 'txt', 'md'])
const MAX_SIZE_BYTES = 10 * 1024 * 1024

const pasteText = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const dragCounter = ref(0)
const isDragging = computed(() => dragCounter.value > 0)
const selectedFile = ref<File | null>(null)

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

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
}

function submitFile(file: File) {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!ALLOWED_EXT.has(ext)) {
    emit('validationError', '仅支持 PDF / DOCX / TXT / MD 文件')
    return
  }
  if (file.size > MAX_SIZE_BYTES) {
    emit('validationError', '文件大小不能超过 10 MB')
    return
  }
  selectedFile.value = file
  pasteText.value = ''
  emit('fileSubmit', file)
}

function handleReparse() {
  if (selectedFile.value) emit('fileSubmit', selectedFile.value)
}

function handleRemoveFile() {
  selectedFile.value = null
  emit('clear')
}
</script>
