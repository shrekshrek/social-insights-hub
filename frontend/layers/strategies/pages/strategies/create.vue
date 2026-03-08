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
          <p class="text-gray-600 dark:text-gray-400 mt-1">填写品牌基本信息，AI 将在下一步协助规划监测方案</p>
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

    <!-- Brief 文档上传卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold">上传 Brief 文档（可选）</h2>
            <p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              支持 PDF、DOCX、TXT、MD，AI 将自动提取信息填入下方表单
            </p>
          </div>
        </div>
      </template>

      <div
        class="border-2 border-dashed rounded-lg transition-colors"
        :class="isDragOver
          ? 'border-primary-400 bg-primary-50 dark:bg-primary-950'
          : 'border-gray-200 dark:border-gray-700'"
        @dragover.prevent="isDragOver = true"
        @dragleave.prevent="isDragOver = false"
        @drop.prevent="handleFileDrop"
      >
        <label class="flex flex-col items-center justify-center gap-3 py-8 cursor-pointer">
          <input
            ref="fileInputRef"
            type="file"
            accept=".pdf,.docx,.txt,.md"
            class="sr-only"
            @change="handleFileChange"
          >

          <template v-if="!parsing">
            <UIcon name="i-heroicons-document-arrow-up" class="w-10 h-10 text-gray-400" />
            <div class="text-center">
              <p class="text-sm font-medium text-gray-700 dark:text-gray-300">
                拖拽文件到此处，或
                <span class="text-primary-600 dark:text-primary-400">点击上传</span>
              </p>
              <p class="text-xs text-gray-400 mt-1">PDF · DOCX · TXT · MD，最大 10 MB</p>
            </div>
          </template>

          <template v-else>
            <UIcon name="i-heroicons-arrow-path" class="w-10 h-10 text-primary-500 animate-spin" />
            <p class="text-sm text-gray-600 dark:text-gray-400">AI 正在解析文档，请稍候…</p>
          </template>
        </label>
      </div>

      <div v-if="parsedFile" class="mt-3 flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
        <UIcon name="i-heroicons-check-circle" class="w-4 h-4 text-success-500" />
        <span>已解析：{{ parsedFile }}</span>
        <UButton
          variant="ghost"
          size="xs"
          icon="i-heroicons-x-mark"
          class="ml-auto"
          @click="clearParsed"
        />
      </div>
    </UCard>

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
        创建后进入 AI 咨询流程，AI 会根据目标规划监测方案，无需提前准备所有信息。
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
