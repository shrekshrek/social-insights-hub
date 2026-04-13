<template>
  <div class="space-y-6">
    <!-- 页眉 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton variant="ghost" icon="i-heroicons-arrow-left" to="/research-agent" />
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">新建研究</h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">填写研究主题，AI 将自动搜索行业报告并生成结构化分析</p>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <UButton variant="outline" :disabled="submitting" to="/research-agent">取消</UButton>
        <UButton
          :loading="submitting"
          icon="i-heroicons-magnifying-glass"
          type="submit"
          form="research-form"
        >
          开始研究
        </UButton>
      </div>
    </div>

    <UCard>
      <template #header>
        <h2 class="text-base font-semibold">研究信息</h2>
      </template>

      <!-- Brief 快速填入 -->
      <BriefUploader
        :loading="extracting || previewing"
        class="mb-5"
        @text-submit="handlePasteText"
        @file-submit="extractFile"
      />

      <UForm
        id="research-form"
        :schema="schema"
        :state="formState"
        class="space-y-4"
        @submit="handleSubmit"
      >
        <div class="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
          <UFormField label="研究标题" name="title" required>
            <UInput v-model="formState.title" placeholder="例如：新能源汽车市场竞争格局" class="w-full" />
          </UFormField>
        </div>

        <UFormField label="研究主题" name="analysis_goal" required>
          <template #description>AI 提炼的核心研究意图，可手动填写或通过 Brief 解析自动生成</template>
          <UTextarea
            v-model="formState.analysis_goal"
            placeholder="例如：了解国内新能源汽车市场的主要玩家、竞争策略及消费者偏好变化趋势"
            :rows="2"
            autoresize
            class="w-full"
          />
        </UFormField>

        <UFormField label="研究问题" name="questions">
          <template #description>AI 将围绕这些问题进行搜索分析，可增删或修改</template>
          <div class="space-y-2">
            <div
              v-for="(_, index) in formState.questions"
              :key="index"
              class="flex items-center gap-2"
            >
              <UInput
                v-model="formState.questions[index]"
                :placeholder="`研究问题 ${index + 1}`"
                class="flex-1"
              />
              <UButton
                variant="ghost"
                color="error"
                icon="i-heroicons-x-mark"
                size="sm"
                @click="removeQuestion(index)"
              />
            </div>
            <UButton
              variant="outline"
              icon="i-heroicons-plus"
              size="sm"
              @click="addQuestion"
            >
              添加问题
            </UButton>
          </div>
        </UFormField>
      </UForm>

      <!-- 关键词 & 搜索角度（仅解析后展示，只读参考） -->
      <div
        v-if="aiExtras"
        class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 pt-4 border-t border-gray-100 dark:border-gray-800"
      >
        <div v-if="aiExtras.keywords.length">
          <p class="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">搜索关键词</p>
          <div class="flex flex-wrap gap-1.5">
            <UBadge v-for="kw in aiExtras.keywords" :key="kw" variant="outline" size="sm">{{ kw }}</UBadge>
          </div>
        </div>
        <div v-if="aiExtras.search_angles.length">
          <p class="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">搜索角度</p>
          <div class="flex flex-wrap gap-1.5">
            <UBadge v-for="angle in aiExtras.search_angles" :key="angle" variant="outline" size="sm" color="neutral">{{ angle }}</UBadge>
          </div>
        </div>
      </div>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import { z } from 'zod'

definePageMeta({ layout: 'default', title: '新建研究' })

const { extractBrief, previewPlan, createTask } = useResearchAgent()
const toast = useToast()

const extracting = ref(false)
const previewing = ref(false)
const submitting = ref(false)

const schema = z.object({
  title: z.string().min(1, '研究标题不能为空').max(200),
  analysis_goal: z.string().min(1, '研究主题不能为空'),
})

type FormState = z.output<typeof schema> & { questions: string[] }

const formState = reactive<FormState>({
  title: '',          // 必填，Zod 校验
  analysis_goal: '',  // 必填，Zod 校验
  questions: [],
})

// 原始 Brief 文本（内部存储，提交时作为 query）
const rawQuery = ref('')

// AI 额外生成的只读参考数据（解析后出现）
const aiExtras = ref<{ keywords: string[]; search_angles: string[] } | null>(null)

function removeQuestion(index: number) {
  formState.questions = formState.questions.filter((_, i) => i !== index)
}

function addQuestion() {
  formState.questions = [...formState.questions, '']
}

async function callPreviewPlan(query: string) {
  previewing.value = true
  try {
    const result = await previewPlan({ analysis_goal: query.trim() })
    if (result.title) formState.title = result.title
    if (result.analysis_goal) formState.analysis_goal = result.analysis_goal
    if (result.research_questions.length) formState.questions = [...result.research_questions]
    aiExtras.value = { keywords: result.keywords, search_angles: result.search_angles }
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    previewing.value = false
  }
}

async function handlePasteText(text: string) {
  rawQuery.value = text
  await callPreviewPlan(text)
}

const ALLOWED_EXT = new Set(['pdf', 'docx', 'txt', 'md'])
async function extractFile(file: File) {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!ALLOWED_EXT.has(ext)) {
    toast.add({ title: '仅支持 PDF / DOCX / TXT / MD 文件', color: 'error' })
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    toast.add({ title: '文件大小不能超过 10 MB', color: 'error' })
    return
  }
  extracting.value = true
  try {
    const result = await extractBrief(file)
    rawQuery.value = result.text
    await callPreviewPlan(result.text)
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    extracting.value = false
  }
}

async function handleSubmit() {
  const validQuestions = formState.questions.filter(q => q.trim())
  submitting.value = true
  try {
    const task = await createTask({
      analysis_goal: formState.analysis_goal.trim(),
      title: formState.title.trim(),
      brief: rawQuery.value.trim() || undefined,
      research_questions: validQuestions.length ? validQuestions : undefined,
    })
    toast.add({ title: `研究任务 #${task.id} 已创建，后台执行中`, color: 'success' })
    navigateTo(`/research-agent/${task.id}`)
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    submitting.value = false
  }
}
</script>
