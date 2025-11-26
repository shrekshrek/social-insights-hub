<script setup lang="ts">
definePageMeta({
  layout: 'default',
})

const route = useRoute()
const taskId = computed(() => Number(route.params.id))

const { getTask } = useTasks()
const { uploadJSONData, validateJSONData } = useJSONUpload()

const { data: task } = getTask(taskId.value)

const contentsFile = ref<File | null>(null)
const commentsFile = ref<File | null>(null)
const contentsData = ref<Record<string, unknown>[] | null>(null)
const commentsData = ref<Record<string, unknown>[] | null>(null)
const validationResult = ref<{ valid: boolean; data?: JSONUploadData; error?: string }>()
const uploading = ref(false)
const isDraggingContents = ref(false)
const isDraggingComments = ref(false)

// 处理contents文件选择
const handleContentsFileSelect = async (file: File) => {
  if (!file.name.endsWith('.json')) {
    validationResult.value = { valid: false, error: 'Contents文件必须是JSON格式' }
    return
  }

  contentsFile.value = file

  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const content = e.target?.result as string
      const data = JSON.parse(content)

      // 判断是数组还是包含contents字段的对象
      if (Array.isArray(data)) {
        contentsData.value = data
      } else if (data.contents && Array.isArray(data.contents)) {
        contentsData.value = data.contents
      } else {
        validationResult.value = { valid: false, error: 'Contents文件格式错误：应该是数组或包含contents字段的对象' }
        return
      }

      validateCombinedData()
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : '未知错误'
      validationResult.value = { valid: false, error: `Contents文件解析失败: ${message}` }
    }
  }
  reader.onerror = () => {
    validationResult.value = { valid: false, error: 'Contents文件读取失败' }
  }
  reader.readAsText(file)
}

// 处理comments文件选择
const handleCommentsFileSelect = async (file: File) => {
  if (!file.name.endsWith('.json')) {
    validationResult.value = { valid: false, error: 'Comments文件必须是JSON格式' }
    return
  }

  commentsFile.value = file

  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const content = e.target?.result as string
      const data = JSON.parse(content)

      // 判断是数组还是包含comments字段的对象
      if (Array.isArray(data)) {
        commentsData.value = data
      } else if (data.comments && Array.isArray(data.comments)) {
        commentsData.value = data.comments
      } else {
        validationResult.value = { valid: false, error: 'Comments文件格式错误：应该是数组或包含comments字段的对象' }
        return
      }

      validateCombinedData()
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : '未知错误'
      validationResult.value = { valid: false, error: `Comments文件解析失败: ${message}` }
    }
  }
  reader.onerror = () => {
    validationResult.value = { valid: false, error: 'Comments文件读取失败' }
  }
  reader.readAsText(file)
}

// 验证合并后的数据
// 注意：后端适配器会处理字段映射，前端直接上传原始数据
const validateCombinedData = () => {
  if (!contentsData.value || !commentsData.value) {
    return // 等待两个文件都上传
  }

  // 直接使用原始数据，后端适配器会自动转换字段
  const combinedData = {
    contents: contentsData.value,
    comments: commentsData.value,
  }

  const jsonStr = JSON.stringify(combinedData)
  validationResult.value = validateJSONData(jsonStr)
}

// 从input选择文件
const handleContentsInput = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) {
    handleContentsFileSelect(file)
  }
}

const handleCommentsInput = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) {
    handleCommentsFileSelect(file)
  }
}

// Contents拖放处理
const handleContentsDrop = (event: DragEvent) => {
  event.preventDefault()
  isDraggingContents.value = false

  const file = event.dataTransfer?.files[0]
  if (file) {
    handleContentsFileSelect(file)
  }
}

const handleContentsDragOver = (event: DragEvent) => {
  event.preventDefault()
  isDraggingContents.value = true
}

const handleContentsDragLeave = () => {
  isDraggingContents.value = false
}

// Comments拖放处理
const handleCommentsDrop = (event: DragEvent) => {
  event.preventDefault()
  isDraggingComments.value = false

  const file = event.dataTransfer?.files[0]
  if (file) {
    handleCommentsFileSelect(file)
  }
}

const handleCommentsDragOver = (event: DragEvent) => {
  event.preventDefault()
  isDraggingComments.value = true
}

const handleCommentsDragLeave = () => {
  isDraggingComments.value = false
}

// 清除选择
const handleClear = () => {
  contentsFile.value = null
  commentsFile.value = null
  contentsData.value = null
  commentsData.value = null
  validationResult.value = undefined
}

// 上传数据
const handleUpload = async () => {
  if (!validationResult.value?.valid || !validationResult.value?.data) {
    return
  }

  uploading.value = true
  try {
    await uploadJSONData(taskId.value, validationResult.value.data)
    await navigateTo(`/social-media/tasks/${taskId.value}`)
  } catch (error) {
    console.error('上传失败:', error)
  } finally {
    uploading.value = false
  }
}

</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center gap-3">
      <UButton variant="ghost" icon="i-heroicons-arrow-left" @click="navigateTo(`/social-media/tasks/${taskId}`)" />
      <div>
        <h1 class="text-2xl font-bold">上传JSON数据</h1>
        <p class="text-gray-600 mt-1">{{ task?.name }}</p>
      </div>
    </div>

    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">上传JSON文件</h2>
          <UButton
            v-if="contentsFile || commentsFile"
            variant="ghost"
            icon="i-heroicons-x-mark"
            @click="handleClear"
          >
            清除全部
          </UButton>
        </div>
      </template>

      <div class="space-y-6">
        <!-- Contents文件上传区域 -->
        <div>
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            1. 上传 Contents 文件 (帖子数据)
          </h3>
          <div v-if="!contentsFile">
            <div
              class="border-2 border-dashed rounded-lg p-8 text-center transition-colors"
              :class="{
                'border-primary-500 bg-primary-50 dark:bg-primary-900/10': isDraggingContents,
                'border-gray-300 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-600': !isDraggingContents
              }"
              @drop="handleContentsDrop"
              @dragover="handleContentsDragOver"
              @dragleave="handleContentsDragLeave"
            >
              <UIcon name="i-heroicons-document-arrow-up" class="w-10 h-10 mx-auto mb-3 text-gray-400" />
              <h4 class="text-base font-medium mb-2">
                拖放 Contents 文件到此处
              </h4>
              <p class="text-gray-600 dark:text-gray-400 mb-3 text-sm">
                或者
              </p>
              <label class="cursor-pointer">
                <UButton size="sm" icon="i-heroicons-folder-open">
                  选择文件
                </UButton>
                <input
                  type="file"
                  accept=".json"
                  class="hidden"
                  @change="handleContentsInput"
                >
              </label>
              <p class="text-xs text-gray-500 mt-3">
                例如：1_search_contents.json
              </p>
            </div>
          </div>
          <div v-else class="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
            <div class="flex items-center gap-3">
              <UIcon name="i-heroicons-document-text" class="w-8 h-8 text-green-500" />
              <div class="flex-1">
                <h4 class="font-medium">{{ contentsFile.name }}</h4>
                <p class="text-sm text-gray-600 dark:text-gray-400">
                  {{ (contentsFile.size / 1024).toFixed(2) }} KB
                  <span v-if="contentsData" class="ml-2">• {{ contentsData.length }} 个帖子</span>
                </p>
              </div>
              <UIcon name="i-heroicons-check-circle" class="w-6 h-6 text-green-500" />
            </div>
          </div>
        </div>

        <!-- Comments文件上传区域 -->
        <div>
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            2. 上传 Comments 文件 (评论数据)
          </h3>
          <div v-if="!commentsFile">
            <div
              class="border-2 border-dashed rounded-lg p-8 text-center transition-colors"
              :class="{
                'border-primary-500 bg-primary-50 dark:bg-primary-900/10': isDraggingComments,
                'border-gray-300 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-600': !isDraggingComments
              }"
              @drop="handleCommentsDrop"
              @dragover="handleCommentsDragOver"
              @dragleave="handleCommentsDragLeave"
            >
              <UIcon name="i-heroicons-document-arrow-up" class="w-10 h-10 mx-auto mb-3 text-gray-400" />
              <h4 class="text-base font-medium mb-2">
                拖放 Comments 文件到此处
              </h4>
              <p class="text-gray-600 dark:text-gray-400 mb-3 text-sm">
                或者
              </p>
              <label class="cursor-pointer">
                <UButton size="sm" icon="i-heroicons-folder-open">
                  选择文件
                </UButton>
                <input
                  type="file"
                  accept=".json"
                  class="hidden"
                  @change="handleCommentsInput"
                >
              </label>
              <p class="text-xs text-gray-500 mt-3">
                例如：1_search_comments.json
              </p>
            </div>
          </div>
          <div v-else class="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
            <div class="flex items-center gap-3">
              <UIcon name="i-heroicons-document-text" class="w-8 h-8 text-green-500" />
              <div class="flex-1">
                <h4 class="font-medium">{{ commentsFile.name }}</h4>
                <p class="text-sm text-gray-600 dark:text-gray-400">
                  {{ (commentsFile.size / 1024).toFixed(2) }} KB
                  <span v-if="commentsData" class="ml-2">• {{ commentsData.length }} 条评论</span>
                </p>
              </div>
              <UIcon name="i-heroicons-check-circle" class="w-6 h-6 text-green-500" />
            </div>
          </div>
        </div>

        <!-- 验证结果 -->
        <div v-if="validationResult">
          <UAlert
            v-if="validationResult.valid && validationResult.data"
            color="success"
            icon="i-heroicons-check-circle"
            title="验证通过"
          >
            <template #description>
              <div class="space-y-1">
                <p>两个文件都已成功加载，数据格式正确，准备上传</p>
                <p class="text-sm">
                  共 {{ validationResult.data.contents.length }} 个帖子和 {{ validationResult.data.comments.length }} 条评论
                </p>
              </div>
            </template>
          </UAlert>
          <UAlert
            v-else
            color="error"
            icon="i-heroicons-x-circle"
            title="验证失败"
            :description="validationResult.error"
          />
        </div>

        <!-- 上传按钮 -->
        <div class="flex justify-end gap-3">
          <UButton
            variant="outline"
            :disabled="!contentsFile && !commentsFile"
            @click="handleClear"
          >
            重新选择
          </UButton>
          <UButton
            v-if="validationResult?.valid"
            :loading="uploading"
            icon="i-heroicons-arrow-up-tray"
            @click="handleUpload"
          >
            上传数据
          </UButton>
        </div>

        <!-- 支持的平台提示 -->
        <div class="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
          <p class="text-sm text-blue-800 dark:text-blue-200 font-medium mb-1">
            支持的平台
          </p>
          <p class="text-xs text-blue-700 dark:text-blue-300">
            抖音、微博、小红书、B站、知乎、快手、贴吧。直接上传爬虫原始导出的 JSON 文件，系统会自动识别并转换字段。
          </p>
        </div>
      </div>
    </UCard>
  </div>
</template>
