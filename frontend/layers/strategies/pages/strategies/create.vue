<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          to="/strategies"
        />
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">新建策略</h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">填写品牌基本信息，AI 将协助设计研究计划并自动采集数据</p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <UButton variant="outline" :disabled="submitting" to="/strategies">
          取消
        </UButton>
        <UButton :loading="submitting" type="submit" form="strategy-form">
          创建
        </UButton>
      </div>
    </div>

    <!-- 品牌信息表单 -->
    <UCard>
      <template #header>
        <h2 class="text-base font-semibold">品牌信息</h2>
      </template>

      <UForm
        id="strategy-form"
        :schema="schema"
        :state="formState"
        @submit="handleSubmit"
      >
        <div class="space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
            <UFormField label="策略名称" name="name" required>
              <UInput
                v-model="formState.name"
                placeholder="例如: 品牌年度营销策略"
                class="w-full"
              />
            </UFormField>

            <UFormField label="品牌 / 产品" name="brand_name" required>
              <UInput
                v-model="formState.brand_name"
                placeholder="例如: 品牌名或具体产品名"
                class="w-full"
              />
            </UFormField>
          </div>

          <UFormField label="分析目标" name="analysis_goal" required>
            <UTextarea
              v-model="formState.analysis_goal"
              placeholder="简述你想通过社媒数据解决的问题，例如:&#10;了解目标消费者的核心痛点与需求，找到品牌差异化切入机会"
              :rows="3"
              class="w-full"
            />
          </UFormField>

          <UFormField label="补充说明" name="constraints">
            <UTextarea
              v-model="formState.constraints"
              placeholder="可选，例如: 主要竞品、重点关注平台、数据时间范围等（不确定的部分可留给 AI 咨询阶段补充）"
              :rows="2"
              class="w-full"
            />
          </UFormField>
        </div>
      </UForm>

      <p class="text-xs text-gray-400 mt-4">
        创建后进入 AI 研究设计流程，系统将自动规划采集方案、创建监测和切片。
      </p>
    </UCard>

    <!-- 上传 Brief 文档 -->
    <UCard>
      <template #header>
        <h2 class="text-base font-semibold">上传 Brief 文档</h2>
      </template>

      <div
        class="border-2 border-dashed rounded-lg p-6 text-center transition-colors"
        :class="isDragOver ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20' : 'border-gray-300 dark:border-gray-700'"
        @dragover.prevent="isDragOver = true"
        @dragleave="isDragOver = false"
        @drop.prevent="handleFileDrop"
      >
        <div v-if="parsing" class="space-y-2">
          <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 mx-auto text-primary-500 animate-spin" />
          <p class="text-sm text-gray-500">正在解析文档...</p>
        </div>
        <div v-else-if="parsedFile" class="space-y-2">
          <UIcon name="i-heroicons-check-circle" class="w-8 h-8 mx-auto text-green-500" />
          <p class="text-sm text-gray-700 dark:text-gray-300">已解析: {{ parsedFile }}</p>
          <UButton variant="ghost" size="xs" @click="clearParsed">清除</UButton>
        </div>
        <div v-else class="space-y-2">
          <UIcon name="i-heroicons-document-arrow-up" class="w-8 h-8 mx-auto text-gray-400" />
          <p class="text-sm text-gray-500">拖拽文件到此处，或</p>
          <UButton variant="outline" size="sm" @click="fileInputRef?.click()">选择文件</UButton>
          <p class="text-xs text-gray-400">支持 PDF、DOCX、TXT、MD，最大 10 MB</p>
        </div>
      </div>

      <input
        ref="fileInputRef"
        type="file"
        accept=".pdf,.docx,.txt,.md"
        class="hidden"
        @change="handleFileChange"
      >

      <p class="text-xs text-gray-400 mt-3">
        上传后 AI 将自动提取品牌信息填入上方表单，可手动修改。
      </p>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import { z } from 'zod'

definePageMeta({
  layout: 'default',
  title: '新建策略',
})

const schema = z.object({
  name: z.string().min(1, '策略名称不能为空').max(255, '策略名称不能超过255个字符'),
  brand_name: z.string().min(1, '品牌/产品名不能为空'),
  analysis_goal: z.string().min(1, '分析目标不能为空'),
  constraints: z.string().optional(),
})

type FormState = z.output<typeof schema>

const strategiesApi = useStrategies()
const submitting = ref(false)
const parsing = ref(false)
const isDragOver = ref(false)
const parsedFile = ref<string | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

const formState = reactive<FormState>({
  name: '',
  brand_name: '',
  analysis_goal: '',
  constraints: '',
})

const ALLOWED_EXTENSIONS = new Set(['pdf', 'docx', 'txt', 'md'])

const validateFile = (file: File): string | null => {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!ALLOWED_EXTENSIONS.has(ext)) return '请上传 PDF、DOCX、TXT 或 MD 文件'
  if (file.size > 10 * 1024 * 1024) return '文件大小不能超过 10 MB'
  return null
}

const applyParsedResult = (result: { strategy_name: string; brand_name: string; analysis_goal: string; constraints: string }) => {
  if (result.strategy_name) formState.name = result.strategy_name
  if (result.brand_name) formState.brand_name = result.brand_name
  if (result.analysis_goal) formState.analysis_goal = result.analysis_goal
  if (result.constraints) formState.constraints = result.constraints
}

const parseFile = async (file: File) => {
  const error = validateFile(file)
  if (error) {
    const toast = useToast()
    toast.add({ title: error, color: 'error' })
    return
  }

  parsing.value = true
  try {
    const result = await strategiesApi.parseBrief(file)
    applyParsedResult(result)
    parsedFile.value = file.name
  } catch {
    // 错误已由 useApi 自动处理
  } finally {
    parsing.value = false
  }
}

const handleFileChange = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) parseFile(file)
  // Reset so same file can be re-uploaded
  if (fileInputRef.value) fileInputRef.value.value = ''
}

const handleFileDrop = (event: DragEvent) => {
  isDragOver.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) parseFile(file)
}

const clearParsed = () => {
  parsedFile.value = null
}

const handleSubmit = async () => {
  submitting.value = true
  try {
    const result = await strategiesApi.createStrategy({
      name: formState.name.trim(),
      brand_brief: {
        brand_name: formState.brand_name.trim(),
        analysis_goal: formState.analysis_goal.trim(),
        ...(formState.constraints?.trim() && { constraints: formState.constraints.trim() }),
      },
    })
    navigateTo(`/strategies/${result.id}`)
  } catch {
    // 错误已由 useApi 自动处理
  } finally {
    submitting.value = false
  }
}
</script>
