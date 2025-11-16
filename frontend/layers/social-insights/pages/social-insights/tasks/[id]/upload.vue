<script setup lang="ts">
import type { JSONUploadData } from '../../../../types'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const taskId = computed(() => Number(route.params.id))

const { getTask } = useTasks()
const { uploadJSONData, validateJSONData } = useJSONUpload()

const { data: task } = getTask(taskId.value)

const jsonContent = ref('')
const validationResult = ref<{ valid: boolean; data?: JSONUploadData; error?: string }>()
const uploading = ref(false)

// 验证JSON
const handleValidate = () => {
  validationResult.value = validateJSONData(jsonContent.value)
}

// 上传数据
const handleUpload = async () => {
  if (!validationResult.value?.valid || !validationResult.value?.data) {
    return
  }

  uploading.value = true
  try {
    await uploadJSONData(taskId.value, validationResult.value.data)
    await navigateTo(`/social-insights/tasks/${taskId.value}`)
  } catch (error) {
    console.error('上传失败:', error)
  } finally {
    uploading.value = false
  }
}

// 从文件加载
const handleFileUpload = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return

  const reader = new FileReader()
  reader.onload = (e) => {
    jsonContent.value = e.target?.result as string
    handleValidate()
  }
  reader.readAsText(file)
}

// 示例数据
const exampleJSON = {
  contents: [
    {
      post_id_on_platform: "BV1234567890",
      title: "示例标题",
      content: "示例内容",
      author_name: "作者名",
      likes_count: 100,
      comments_count: 10,
      shares_count: 5,
      views_count: 1000
    }
  ],
  comments: [
    {
      comment_id_on_platform: "comment_001",
      content: "示例评论",
      author_name: "评论者",
      likes_count: 5,
      raw_data: { post_id_on_platform: "BV1234567890" }
    }
  ]
}

const loadExample = () => {
  jsonContent.value = JSON.stringify(exampleJSON, null, 2)
  handleValidate()
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center gap-3">
      <UButton variant="ghost" icon="i-heroicons-arrow-left" @click="navigateTo(`/social-insights/tasks/${taskId}`)" />
      <div>
        <h1 class="text-2xl font-bold">上传JSON数据</h1>
        <p class="text-gray-600 mt-1">{{ task?.name }}</p>
      </div>
    </div>

    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">JSON数据</h2>
          <div class="flex gap-2">
            <label class="cursor-pointer">
              <UButton variant="outline" icon="i-heroicons-document-arrow-up">选择文件</UButton>
              <input type="file" accept=".json" class="hidden" @change="handleFileUpload">
            </label>
            <UButton variant="outline" @click="loadExample">加载示例</UButton>
            <UButton @click="handleValidate">验证</UButton>
          </div>
        </div>
      </template>

      <UTextarea v-model="jsonContent" :rows="20" placeholder="粘贴或上传JSON数据..." class="font-mono text-sm" />

      <template #footer>
        <div v-if="validationResult" class="space-y-4">
          <UAlert v-if="validationResult.valid && validationResult.data" color="green" icon="i-heroicons-check-circle" title="验证通过" :description="`检测到 ${validationResult.data.contents.length} 个帖子和 ${validationResult.data.comments.length} 条评论`" />
          <UAlert v-else color="red" icon="i-heroicons-x-circle" title="验证失败" :description="validationResult.error" />
          <UButton v-if="validationResult.valid" :loading="uploading" @click="handleUpload">上传数据</UButton>
        </div>
      </template>
    </UCard>

    <UCard>
      <template #header><h2 class="text-lg font-semibold">数据格式说明</h2></template>
      <div class="prose prose-sm dark:prose-invert max-w-none">
        <p>JSON数据应包含两个主要字段：</p>
        <ul>
          <li><strong>contents</strong>: 帖子数组，每个帖子必须包含 post_id_on_platform</li>
          <li><strong>comments</strong>: 评论数组，每个评论必须包含 comment_id_on_platform 和 raw_data.post_id_on_platform 用于关联帖子</li>
        </ul>
      </div>
    </UCard>
  </div>
</template>
