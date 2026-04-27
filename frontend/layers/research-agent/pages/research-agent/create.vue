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
        :loading="parsing"
        class="mb-5"
        @text-submit="handlePasteText"
        @file-submit="handleParseFile"
        @clear="clearSuitability"
        @validation-error="showError"
      />

      <!-- 研究类型选择 -->
      <div class="mb-5">
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">研究类型</label>
        <div class="flex flex-wrap gap-2">
          <UButton
            v-for="opt in profileOptions"
            :key="opt.name"
            :variant="formState.profile_name === opt.name ? 'solid' : 'outline'"
            :color="formState.profile_name === opt.name ? 'primary' : 'neutral'"
            size="sm"
            @click="formState.profile_name = opt.name"
          >
            {{ opt.display_name }}
          </UButton>
        </div>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-2">
          {{ profileHint }}
        </p>
      </div>

      <!-- 适配度诊断 banner -->
      <div v-if="suitability && bannerKind" class="mb-5">
        <div
          v-if="bannerKind === 'switch'"
          class="flex items-start gap-2.5 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-sm"
        >
          <UIcon name="i-heroicons-light-bulb" class="w-4 h-4 mt-0.5 text-amber-500 flex-shrink-0" />
          <div class="flex-1">
            <div class="font-medium text-amber-700 dark:text-amber-300">
              建议切换到「{{ PROFILE_DISPLAY[suitability.recommended_profile] ?? suitability.recommended_profile }}」
            </div>
            <p v-if="suitability.note" class="text-gray-600 dark:text-gray-400 mt-0.5">{{ suitability.note }}</p>
            <UButton size="xs" variant="subtle" class="mt-2" icon="i-heroicons-arrow-path" @click="applyRecommendedProfile">
              切换并重新解析
            </UButton>
          </div>
        </div>

        <div
          v-else-if="bannerKind === 'redirect'"
          class="flex items-start gap-2.5 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-sm"
        >
          <UIcon name="i-heroicons-x-circle" class="w-4 h-4 mt-0.5 text-red-500 flex-shrink-0" />
          <div class="flex-1">
            <div class="font-medium text-red-700 dark:text-red-300">这条 Brief 不适合走专题研究</div>
            <p v-if="suitability.note" class="text-gray-600 dark:text-gray-400 mt-0.5">{{ suitability.note }}</p>
            <UButton
              v-if="REDIRECT_TARGETS[suitability.redirect_hint]"
              size="xs"
              variant="subtle"
              class="mt-2"
              :to="REDIRECT_TARGETS[suitability.redirect_hint]!.path"
              :label="REDIRECT_TARGETS[suitability.redirect_hint]!.label"
              icon="i-heroicons-arrow-right"
              trailing
            />
          </div>
        </div>

        <div
          v-else-if="bannerKind === 'partial'"
          class="flex items-start gap-2.5 p-3 rounded-lg bg-gray-100 dark:bg-gray-800 text-sm"
        >
          <UIcon name="i-heroicons-information-circle" class="w-4 h-4 mt-0.5 text-gray-500 flex-shrink-0" />
          <div class="flex-1">
            <div class="font-medium text-gray-700 dark:text-gray-300">Brief 信息不足</div>
            <p v-if="suitability.note" class="text-gray-600 dark:text-gray-400 mt-0.5">{{ suitability.note }}</p>
          </div>
        </div>
      </div>

      <UForm
        id="research-form"
        :schema="schema"
        :state="formState"
        class="space-y-4"
        @submit="handleSubmit"
      >
        <div class="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
          <UFormField label="研究标题" name="title" required>
            <UInput v-model="formState.title" :placeholder="titlePlaceholder" class="w-full" />
          </UFormField>
        </div>

        <UFormField label="研究主题" name="analysis_goal" required>
          <UTextarea
            v-model="formState.analysis_goal"
            :placeholder="goalPlaceholder"
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
import type {
  ResearchProfileOption,
  SuitabilityVerdict,
  SuitabilityRedirectHint,
  ParseBriefResponse,
} from '../../types'

definePageMeta({ layout: 'default', title: '新建研究' })

const { getProfiles, parseBrief, parseBriefText, createTask } = useResearchAgentApi()
const { showError } = useApi()
const toast = useToast()

const parsing = ref(false)
const submitting = ref(false)

// 研究类型列表（后端驱动）
const { data: profilesData } = await getProfiles()
const profileOptions = computed<ResearchProfileOption[]>(() => profilesData.value ?? [
  { name: 'industry', display_name: '行业研究' },
  { name: 'creative', display_name: '创意研究' },
])

const schema = z.object({
  title: z.string().min(1, '研究标题不能为空').max(200),
  analysis_goal: z.string().min(1, '研究主题不能为空'),
})

type FormState = z.output<typeof schema> & { questions: string[]; profile_name: string }

// 支持从 URL query 预选 profile（如策略页 insufficient 分诊跳转时指定）
const route = useRoute()
const initialProfile = (() => {
  const q = route.query.profile
  const requested = Array.isArray(q) ? q[0] : q
  const valid = profileOptions.value.some((opt) => opt.name === requested)
  return valid && typeof requested === 'string' ? requested : 'industry'
})()

const formState = reactive<FormState>({
  title: '',          // 必填，Zod 校验
  analysis_goal: '',  // 必填，Zod 校验
  questions: [],
  profile_name: initialProfile,
})

// 研究类型影响的展示文案
const PROFILE_PRESETS: Record<string, { hint: string; title: string; goal: string }> = {
  industry: {
    hint: '面向行业报告/白皮书/权威数据，适合市场规模、竞争格局、政策研究等专业分析。',
    title: '例如：新能源汽车市场竞争格局',
    goal: '例如：了解国内新能源汽车市场的主要玩家、竞争策略及消费者偏好变化趋势',
  },
  creative: {
    hint: '面向 campaign 案例、创意评论与品牌叙事，适合创意团队与策划找灵感参考。',
    title: '例如：新消费品牌春节 campaign 创意参考',
    goal: '例如：收集近年新消费品牌在春节节点的 campaign 创意做法，提炼可借鉴的视觉/文案钩子与传播机制',
  },
}
const profileHint = computed(() => PROFILE_PRESETS[formState.profile_name]?.hint ?? '')
const titlePlaceholder = computed(() => PROFILE_PRESETS[formState.profile_name]?.title ?? '请输入研究标题')
const goalPlaceholder = computed(() => PROFILE_PRESETS[formState.profile_name]?.goal ?? '请输入研究主题')

// 原始 Brief 文本（内部存储，提交时作为 query）
const rawQuery = ref('')

// AI 额外生成的只读参考数据（解析后出现）
const aiExtras = ref<{ keywords: string[]; search_angles: string[] } | null>(null)

// 适配度诊断结果（解析后出现，呈现于 banner）
interface SuitabilityState {
  verdict: SuitabilityVerdict
  recommended_profile: string
  redirect_hint: SuitabilityRedirectHint
  note: string
}
const suitability = ref<SuitabilityState | null>(null)

const PROFILE_DISPLAY: Record<string, string> = {
  industry: '行业研究',
  creative: '创意研究',
}

const REDIRECT_TARGETS: Record<string, { path: string; label: string }> = {
  strategy: { path: '/strategies/create', label: '前往策略页' },
  monitor_social: { path: '/social-media/monitors/create', label: '前往社媒监测' },
  monitor_news: { path: '/news-media/monitors/create', label: '前往新闻监测' },
}

const bannerKind = computed<'switch' | 'redirect' | 'partial' | null>(() => {
  const s = suitability.value
  if (!s) return null
  if (s.verdict === 'suitable' && s.recommended_profile && s.recommended_profile !== formState.profile_name) {
    return 'switch'
  }
  if (s.verdict === 'not_suitable' && s.redirect_hint) {
    return 'redirect'
  }
  if (s.verdict === 'partial') {
    return 'partial'
  }
  return null
})

function applyRecommendedProfile() {
  const target = suitability.value?.recommended_profile
  if (target && target !== formState.profile_name) {
    formState.profile_name = target
    // profile 变更会触发下面 watch，自动重新调用 callPreviewPlan
  }
}

function clearSuitability() {
  suitability.value = null
  aiExtras.value = null
  rawQuery.value = ''
  formState.title = ''
  formState.analysis_goal = ''
  formState.questions = []
}

function removeQuestion(index: number) {
  formState.questions = formState.questions.filter((_, i) => i !== index)
}

function addQuestion() {
  formState.questions = [...formState.questions, '']
}

function applyParseResult(result: ParseBriefResponse) {
  if (result.title) formState.title = result.title
  if (result.analysis_goal) formState.analysis_goal = result.analysis_goal
  if (result.research_questions.length) formState.questions = [...result.research_questions]
  aiExtras.value = { keywords: result.keywords, search_angles: result.search_angles }
  suitability.value = {
    verdict: result.verdict,
    recommended_profile: result.recommended_profile,
    redirect_hint: result.redirect_hint,
    note: result.note,
  }
  rawQuery.value = result.brief_text
}

async function handlePasteText(text: string) {
  parsing.value = true
  try {
    const result = await parseBriefText({ text, profile_name: formState.profile_name })
    applyParseResult(result)
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    parsing.value = false
  }
}

async function handleParseFile(file: File) {
  parsing.value = true
  try {
    const result = await parseBrief(file, formState.profile_name)
    applyParseResult(result)
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    parsing.value = false
  }
}


// profile 切换时（含 banner 触发）若已有 brief 则用文本入口重新解析
// 文件入口的抽取文本已在 brief_text 中回流到 rawQuery，无需重新上传
watch(() => formState.profile_name, (next, prev) => {
  if (next === prev) return
  if (!rawQuery.value.trim()) return
  handlePasteText(rawQuery.value)
})

async function handleSubmit() {
  const validQuestions = formState.questions.filter(q => q.trim())
  submitting.value = true
  try {
    const task = await createTask({
      analysis_goal: formState.analysis_goal.trim(),
      title: formState.title.trim(),
      brief: rawQuery.value.trim() || undefined,
      research_questions: validQuestions.length ? validQuestions : undefined,
      profile_name: formState.profile_name,
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
