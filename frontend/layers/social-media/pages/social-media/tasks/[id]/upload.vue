<script setup lang="ts">
definePageMeta({
  layout: 'default',
})

const route = useRoute()
const taskId = computed(() => Number(route.params.id))

const { getTask } = useTasks()
const { uploadJSONData, validateJSONData } = useJSONUpload()

const { data: task } = getTask(taskId.value)

// 多文件状态
const contentsFiles = ref<File[]>([])
const commentsFiles = ref<File[]>([])
const contentsData = ref<Record<string, unknown>[]>([])
const commentsData = ref<Record<string, unknown>[]>([])
const validationResult = ref<{ valid: boolean; data?: JSONUploadData; error?: string }>()
const uploading = ref(false)
const isDraggingContents = ref(false)
const isDraggingComments = ref(false)

// 统计信息
const contentsStats = ref<{ total: number; unique: number; duplicates: number }>({ total: 0, unique: 0, duplicates: 0 })
const commentsStats = ref<{ total: number; unique: number; duplicates: number }>({ total: 0, unique: 0, duplicates: 0 })

// 获取帖子数据的唯一标识符（支持多平台）
const getPostUniqueKey = (item: Record<string, unknown>): string => {
  // 尝试多种平台的ID字段
  const idFields = [
    'aweme_id',           // 抖音
    'note_id',            // 小红书
    'mblogid', 'mid',     // 微博
    'bvid', 'aid',        // B站
    'id',                 // 知乎、快手、贴吧
    'post_id_on_platform' // 通用字段
  ]
  
  for (const field of idFields) {
    if (item[field]) {
      return `${field}:${String(item[field])}`
    }
  }
  
  // 如果没有ID字段，使用内容哈希作为备用
  const content = item['desc'] || item['content'] || item['text'] || ''
  return `content:${String(content).slice(0, 100)}`
}

// 获取评论数据的唯一标识符
const getCommentUniqueKey = (item: Record<string, unknown>): string => {
  const idFields = [
    'cid',                // 抖音、快手
    'comment_id',         // 小红书、微博
    'rpid',               // B站
    'id',                 // 知乎、贴吧
  ]
  
  for (const field of idFields) {
    if (item[field]) {
      return `${field}:${String(item[field])}`
    }
  }
  
  // 备用：使用内容+作者组合
  const content = item['text'] || item['content'] || ''
  const user = item['user'] as Record<string, unknown> | undefined
  const author = user?.['nickname'] || user?.['name'] || item['author_name'] || ''
  return `comment:${String(content).slice(0, 50)}:${author}`
}

// 去重并合并数据
const deduplicateData = <T extends Record<string, unknown>>(
  items: T[],
  getKey: (item: T) => string
): { unique: T[]; stats: { total: number; unique: number; duplicates: number } } => {
  const seen = new Map<string, T>()
  const total = items.length
  
  for (const item of items) {
    const key = getKey(item)
    if (!seen.has(key)) {
      seen.set(key, item)
    }
  }
  
  const unique = Array.from(seen.values())
  return {
    unique,
    stats: {
      total,
      unique: unique.length,
      duplicates: total - unique.length
    }
  }
}

// 读取单个文件
const readJsonFile = (file: File): Promise<Record<string, unknown>[]> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string
        const data = JSON.parse(content)
        
        // 支持数组或包含特定字段的对象
        if (Array.isArray(data)) {
          resolve(data)
        } else if (data.contents && Array.isArray(data.contents)) {
          resolve(data.contents)
        } else if (data.comments && Array.isArray(data.comments)) {
          resolve(data.comments)
        } else {
          reject(new Error('文件格式错误：应该是数组或包含 contents/comments 字段的对象'))
        }
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : '未知错误'
        reject(new Error(`JSON 解析失败: ${message}`))
      }
    }
    reader.onerror = () => reject(new Error('文件读取失败'))
    reader.readAsText(file)
  })
}

// 处理多个 contents 文件
const handleContentsFilesSelect = async (files: File[]) => {
  const jsonFiles = files.filter(f => f.name.endsWith('.json'))
  if (jsonFiles.length === 0) {
    validationResult.value = { valid: false, error: 'Contents 文件必须是 JSON 格式' }
    return
  }
  
  // 追加文件到列表
  contentsFiles.value = [...contentsFiles.value, ...jsonFiles]
  
  try {
    // 读取所有新文件
    const allNewData: Record<string, unknown>[] = []
    for (const file of jsonFiles) {
      const data = await readJsonFile(file)
      allNewData.push(...data)
    }
    
    // 合并现有数据和新数据，然后去重
    const combinedData = [...contentsData.value, ...allNewData]
    const { unique, stats } = deduplicateData(combinedData, getPostUniqueKey)
    
    contentsData.value = unique
    contentsStats.value = stats
    
    validateCombinedData()
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : '未知错误'
    validationResult.value = { valid: false, error: `Contents 文件处理失败: ${message}` }
  }
}

// 处理多个 comments 文件
const handleCommentsFilesSelect = async (files: File[]) => {
  const jsonFiles = files.filter(f => f.name.endsWith('.json'))
  if (jsonFiles.length === 0) {
    validationResult.value = { valid: false, error: 'Comments 文件必须是 JSON 格式' }
    return
  }
  
  // 追加文件到列表
  commentsFiles.value = [...commentsFiles.value, ...jsonFiles]
  
  try {
    // 读取所有新文件
    const allNewData: Record<string, unknown>[] = []
    for (const file of jsonFiles) {
      const data = await readJsonFile(file)
      allNewData.push(...data)
    }
    
    // 合并现有数据和新数据，然后去重
    const combinedData = [...commentsData.value, ...allNewData]
    const { unique, stats } = deduplicateData(combinedData, getCommentUniqueKey)
    
    commentsData.value = unique
    commentsStats.value = stats
    
    validateCombinedData()
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : '未知错误'
    validationResult.value = { valid: false, error: `Comments 文件处理失败: ${message}` }
  }
}

// 验证合并后的数据
const validateCombinedData = () => {
  if (contentsData.value.length === 0) {
    validationResult.value = undefined
    return
  }
  
  // 直接使用原始数据，后端适配器会自动转换字段
  const combinedData = {
    contents: contentsData.value,
    comments: commentsData.value,
  }
  
  const jsonStr = JSON.stringify(combinedData)
  validationResult.value = validateJSONData(jsonStr)
}

// 从 input 选择文件（支持多选）
const handleContentsInput = (event: Event) => {
  const files = Array.from((event.target as HTMLInputElement).files || [])
  if (files.length > 0) {
    handleContentsFilesSelect(files)
  }
  // 重置 input 以允许再次选择相同文件
  ;(event.target as HTMLInputElement).value = ''
}

const handleCommentsInput = (event: Event) => {
  const files = Array.from((event.target as HTMLInputElement).files || [])
  if (files.length > 0) {
    handleCommentsFilesSelect(files)
  }
  ;(event.target as HTMLInputElement).value = ''
}

// Contents 拖放处理（支持多文件）
const handleContentsDrop = (event: DragEvent) => {
  event.preventDefault()
  isDraggingContents.value = false
  
  const files = Array.from(event.dataTransfer?.files || [])
  if (files.length > 0) {
    handleContentsFilesSelect(files)
  }
}

const handleContentsDragOver = (event: DragEvent) => {
  event.preventDefault()
  isDraggingContents.value = true
}

const handleContentsDragLeave = () => {
  isDraggingContents.value = false
}

// Comments 拖放处理（支持多文件）
const handleCommentsDrop = (event: DragEvent) => {
  event.preventDefault()
  isDraggingComments.value = false
  
  const files = Array.from(event.dataTransfer?.files || [])
  if (files.length > 0) {
    handleCommentsFilesSelect(files)
  }
}

const handleCommentsDragOver = (event: DragEvent) => {
  event.preventDefault()
  isDraggingComments.value = true
}

const handleCommentsDragLeave = () => {
  isDraggingComments.value = false
}

// 移除单个 contents 文件（需要重新计算数据）
const removeContentsFile = async (index: number) => {
  contentsFiles.value.splice(index, 1)
  
  // 重新读取并合并所有剩余文件
  if (contentsFiles.value.length === 0) {
    contentsData.value = []
    contentsStats.value = { total: 0, unique: 0, duplicates: 0 }
  } else {
    const allData: Record<string, unknown>[] = []
    for (const file of contentsFiles.value) {
      try {
        const data = await readJsonFile(file)
        allData.push(...data)
      } catch {
        // 忽略单个文件读取错误
      }
    }
    const { unique, stats } = deduplicateData(allData, getPostUniqueKey)
    contentsData.value = unique
    contentsStats.value = stats
  }
  
  validateCombinedData()
}

// 移除单个 comments 文件
const removeCommentsFile = async (index: number) => {
  commentsFiles.value.splice(index, 1)
  
  if (commentsFiles.value.length === 0) {
    commentsData.value = []
    commentsStats.value = { total: 0, unique: 0, duplicates: 0 }
  } else {
    const allData: Record<string, unknown>[] = []
    for (const file of commentsFiles.value) {
      try {
        const data = await readJsonFile(file)
        allData.push(...data)
      } catch {
        // 忽略单个文件读取错误
      }
    }
    const { unique, stats } = deduplicateData(allData, getCommentUniqueKey)
    commentsData.value = unique
    commentsStats.value = stats
  }
  
  validateCombinedData()
}

// 清除所有选择
const handleClear = () => {
  contentsFiles.value = []
  commentsFiles.value = []
  contentsData.value = []
  commentsData.value = []
  contentsStats.value = { total: 0, unique: 0, duplicates: 0 }
  commentsStats.value = { total: 0, unique: 0, duplicates: 0 }
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

// 格式化文件大小
const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

// 计算总文件大小
const totalContentsSize = computed(() => 
  contentsFiles.value.reduce((sum, f) => sum + f.size, 0)
)
const totalCommentsSize = computed(() => 
  commentsFiles.value.reduce((sum, f) => sum + f.size, 0)
)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center gap-3">
      <UButton variant="ghost" icon="i-heroicons-arrow-left" :to="`/social-media/tasks/${taskId}`" />
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
            v-if="contentsFiles.length > 0 || commentsFiles.length > 0"
            variant="ghost"
            icon="i-heroicons-x-mark"
            @click="handleClear"
          >
            清除全部
          </UButton>
        </div>
      </template>

      <div class="space-y-6">
        <!-- Contents 文件上传区域 -->
        <div>
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            1. 上传 Contents 文件 (帖子数据) 
            <span class="text-gray-400 font-normal">- 支持多文件，自动去重</span>
          </h3>
          
          <!-- 拖放区域（始终显示，支持继续添加） -->
          <div
            class="border-2 border-dashed rounded-lg p-6 text-center transition-colors mb-3"
            :class="{
              'border-primary-500 bg-primary-50 dark:bg-primary-900/10': isDraggingContents,
              'border-gray-300 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-600': !isDraggingContents
            }"
            @drop="handleContentsDrop"
            @dragover="handleContentsDragOver"
            @dragleave="handleContentsDragLeave"
          >
            <UIcon name="i-heroicons-document-arrow-up" class="w-8 h-8 mx-auto mb-2 text-gray-400" />
            <h4 class="text-sm font-medium mb-1">
              拖放 Contents 文件到此处
            </h4>
            <p class="text-gray-500 dark:text-gray-400 text-xs mb-2">
              支持同时拖入多个文件
            </p>
            <label class="cursor-pointer inline-block">
              <UButton size="xs" icon="i-heroicons-folder-open">
                选择文件
              </UButton>
              <input
                type="file"
                accept=".json"
                multiple
                class="hidden"
                @change="handleContentsInput"
              >
            </label>
          </div>
          
          <!-- 已选择的文件列表 -->
          <div v-if="contentsFiles.length > 0" class="space-y-2">
            <div
              v-for="(file, index) in contentsFiles"
              :key="file.name + index"
              class="flex items-center gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800"
            >
              <UIcon name="i-heroicons-document-text" class="w-5 h-5 text-green-500 shrink-0" />
              <div class="flex-1 min-w-0">
                <p class="font-medium text-sm truncate">{{ file.name }}</p>
                <p class="text-xs text-gray-500">{{ formatFileSize(file.size) }}</p>
              </div>
              <UButton
                size="xs"
                variant="ghost"
                color="error"
                icon="i-heroicons-x-mark"
                @click="removeContentsFile(index)"
              />
            </div>
            
            <!-- 统计信息 -->
            <div class="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
              <div class="flex items-center gap-4 text-sm">
                <span class="text-blue-700 dark:text-blue-300">
                  <strong>{{ contentsFiles.length }}</strong> 个文件
                </span>
                <span class="text-gray-500">|</span>
                <span class="text-blue-700 dark:text-blue-300">
                  总大小: <strong>{{ formatFileSize(totalContentsSize) }}</strong>
                </span>
                <span class="text-gray-500">|</span>
                <span class="text-blue-700 dark:text-blue-300">
                  原始: <strong>{{ contentsStats.total }}</strong> 条
                </span>
                <span v-if="contentsStats.duplicates > 0" class="text-orange-600 dark:text-orange-400">
                  去重: <strong>{{ contentsStats.duplicates }}</strong> 条
                </span>
                <span class="text-green-600 dark:text-green-400">
                  有效: <strong>{{ contentsStats.unique }}</strong> 个帖子
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Comments 文件上传区域 -->
        <div>
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            2. 上传 Comments 文件 (评论数据)
            <span class="text-gray-400 font-normal">- 支持多文件，自动去重（可选）</span>
          </h3>
          
          <!-- 拖放区域 -->
          <div
            class="border-2 border-dashed rounded-lg p-6 text-center transition-colors mb-3"
            :class="{
              'border-primary-500 bg-primary-50 dark:bg-primary-900/10': isDraggingComments,
              'border-gray-300 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-600': !isDraggingComments
            }"
            @drop="handleCommentsDrop"
            @dragover="handleCommentsDragOver"
            @dragleave="handleCommentsDragLeave"
          >
            <UIcon name="i-heroicons-document-arrow-up" class="w-8 h-8 mx-auto mb-2 text-gray-400" />
            <h4 class="text-sm font-medium mb-1">
              拖放 Comments 文件到此处
            </h4>
            <p class="text-gray-500 dark:text-gray-400 text-xs mb-2">
              支持同时拖入多个文件（可选，不上传评论也可以）
            </p>
            <label class="cursor-pointer inline-block">
              <UButton size="xs" icon="i-heroicons-folder-open">
                选择文件
              </UButton>
              <input
                type="file"
                accept=".json"
                multiple
                class="hidden"
                @change="handleCommentsInput"
              >
            </label>
          </div>
          
          <!-- 已选择的文件列表 -->
          <div v-if="commentsFiles.length > 0" class="space-y-2">
            <div
              v-for="(file, index) in commentsFiles"
              :key="file.name + index"
              class="flex items-center gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800"
            >
              <UIcon name="i-heroicons-document-text" class="w-5 h-5 text-green-500 shrink-0" />
              <div class="flex-1 min-w-0">
                <p class="font-medium text-sm truncate">{{ file.name }}</p>
                <p class="text-xs text-gray-500">{{ formatFileSize(file.size) }}</p>
              </div>
              <UButton
                size="xs"
                variant="ghost"
                color="error"
                icon="i-heroicons-x-mark"
                @click="removeCommentsFile(index)"
              />
            </div>
            
            <!-- 统计信息 -->
            <div class="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg border border-purple-200 dark:border-purple-800">
              <div class="flex items-center gap-4 text-sm">
                <span class="text-purple-700 dark:text-purple-300">
                  <strong>{{ commentsFiles.length }}</strong> 个文件
                </span>
                <span class="text-gray-500">|</span>
                <span class="text-purple-700 dark:text-purple-300">
                  总大小: <strong>{{ formatFileSize(totalCommentsSize) }}</strong>
                </span>
                <span class="text-gray-500">|</span>
                <span class="text-purple-700 dark:text-purple-300">
                  原始: <strong>{{ commentsStats.total }}</strong> 条
                </span>
                <span v-if="commentsStats.duplicates > 0" class="text-orange-600 dark:text-orange-400">
                  去重: <strong>{{ commentsStats.duplicates }}</strong> 条
                </span>
                <span class="text-green-600 dark:text-green-400">
                  有效: <strong>{{ commentsStats.unique }}</strong> 条评论
                </span>
              </div>
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
                <p>数据格式正确，准备上传</p>
                <p class="text-sm">
                  共 <strong>{{ validationResult.data.contents.length }}</strong> 个帖子
                  和 <strong>{{ validationResult.data.comments.length }}</strong> 条评论
                  <span v-if="contentsStats.duplicates > 0 || commentsStats.duplicates > 0" class="text-orange-600">
                    （已自动去除 {{ contentsStats.duplicates + commentsStats.duplicates }} 条重复数据）
                  </span>
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
            :disabled="contentsFiles.length === 0 && commentsFiles.length === 0"
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
            <br>
            <strong>多文件支持：</strong>可以一次性拖入多个文件，系统会自动合并并根据平台ID去重。
          </p>
        </div>
      </div>
    </UCard>
  </div>
</template>
