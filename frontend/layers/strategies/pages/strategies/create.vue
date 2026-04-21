<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton variant="ghost" icon="i-heroicons-arrow-left" to="/strategies" />
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">新建策略</h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">填写 Brief，AI 将自动规划研究方案</p>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <UButton variant="outline" :disabled="submitting" to="/strategies">取消</UButton>
        <UButton :loading="submitting" :disabled="platformVerdict === 'insufficient'" icon="i-heroicons-check" type="submit" form="strategy-form">创建策略</UButton>
      </div>
    </div>

    <UCard>
      <template #header>
        <h2 class="text-base font-semibold">Brief 信息</h2>
      </template>

      <!-- AI 快速填入 -->
      <BriefUploader
        :loading="parsing"
        class="mb-5"
        @text-submit="handleParseText"
        @file-submit="parseFile"
      />

      <UForm
        id="strategy-form"
        :schema="schema"
        :state="formState"
        class="space-y-4"
        @submit="handleSubmit"
      >
        <div class="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
          <UFormField label="策略名称" name="name" required>
            <UInput v-model="formState.name" placeholder="例如: 品牌年度营销策略" class="w-full" />
          </UFormField>

          <UFormField label="研究主体" name="subject" required>
            <UInput v-model="formState.subject" placeholder="例如: 品牌名或具体产品名" class="w-full" />
          </UFormField>
        </div>

        <UFormField label="分析目标" name="analysis_goal" required>
          <UTextarea
            v-model="formState.analysis_goal"
            placeholder="简述你想通过社媒数据解决的问题"
            :rows="3"
            class="w-full"
          />
        </UFormField>

        <UFormField label="补充说明" name="constraints">
          <UTextarea
            v-model="formState.constraints"
            placeholder="可选，例如: 主要竞品、重点关注平台、数据时间范围等"
            :rows="2"
            class="w-full"
          />
        </UFormField>
      </UForm>
    </UCard>

    <!-- 渠道分析结果 -->
    <UCard v-if="parsedChannelPlan?.length">
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-signal" class="text-primary-500 w-4 h-4" />
          <h2 class="text-base font-semibold">渠道分析结果</h2>
          <span class="text-xs text-gray-400 font-normal">以下是 AI 对本次研究的渠道建议，供参考</span>
        </div>
      </template>

      <!-- 平台支持度 -->
      <div
        v-if="platformVerdict"
        class="mb-4 flex items-start gap-2.5 p-3 rounded-lg text-sm"
        :class="{
          'bg-green-50 dark:bg-green-900/20': platformVerdict === 'sufficient',
          'bg-amber-50 dark:bg-amber-900/20': platformVerdict === 'partial',
          'bg-red-50 dark:bg-red-900/20': platformVerdict === 'insufficient',
        }"
      >
        <UIcon
          :name="platformVerdict === 'sufficient' ? 'i-heroicons-check-circle' : platformVerdict === 'partial' ? 'i-heroicons-exclamation-triangle' : 'i-heroicons-x-circle'"
          class="w-4 h-4 mt-0.5 flex-shrink-0"
          :class="{
            'text-green-500': platformVerdict === 'sufficient',
            'text-amber-500': platformVerdict === 'partial',
            'text-red-500': platformVerdict === 'insufficient',
          }"
        />
        <div>
          <span
            class="font-medium"
            :class="{
              'text-green-700 dark:text-green-300': platformVerdict === 'sufficient',
              'text-amber-700 dark:text-amber-300': platformVerdict === 'partial',
              'text-red-700 dark:text-red-300': platformVerdict === 'insufficient',
            }"
          >{{ platformVerdict === 'sufficient' ? '当前平台可满足该研究' : platformVerdict === 'partial' ? '当前平台部分支持该研究' : '当前平台暂不适合该研究' }}</span>
          <p v-if="platformNote" class="text-gray-600 dark:text-gray-400 mt-0.5">{{ platformNote }}</p>
          <div v-if="platformVerdict === 'insufficient'" class="mt-2 flex flex-wrap gap-2">
            <UButton
              v-if="insufficientReason === 'no_channel' || insufficientReason === ''"
              to="/research-agent/create"
              label="前往专题研究"
              icon="i-heroicons-arrow-right"
              trailing
              variant="subtle"
              size="xs"
            />
            <UButton
              v-if="insufficientReason === 'knowledge_industry'"
              :to="{ path: '/research-agent/create', query: { profile: 'industry' } }"
              label="前往专题研究 · 行业研究"
              icon="i-heroicons-arrow-right"
              trailing
              variant="subtle"
              size="xs"
            />
            <UButton
              v-if="insufficientReason === 'knowledge_creative'"
              :to="{ path: '/research-agent/create', query: { profile: 'creative' } }"
              label="前往专题研究 · 创意研究"
              icon="i-heroicons-arrow-right"
              trailing
              variant="subtle"
              size="xs"
            />
            <UButton
              v-if="insufficientReason === 'diagnostic_social' || insufficientReason === 'diagnostic_dual'"
              to="/social-media/monitors/create"
              label="前往社媒监测 + 切片分析"
              icon="i-heroicons-arrow-right"
              trailing
              variant="subtle"
              size="xs"
            />
            <UButton
              v-if="insufficientReason === 'diagnostic_news' || insufficientReason === 'diagnostic_dual'"
              to="/news-media/monitors/create"
              label="前往新闻监测 + 切片分析"
              icon="i-heroicons-arrow-right"
              trailing
              variant="subtle"
              size="xs"
            />
          </div>
        </div>
      </div>

      <div v-if="platformVerdict !== 'insufficient'" class="space-y-3">
        <div
          v-for="item in parsedChannelPlan"
          :key="item.type"
          class="rounded-lg border p-3 space-y-2"
          :class="item.available
            ? 'border-primary-200 bg-primary-50 dark:border-primary-800 dark:bg-primary-900/20'
            : 'border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50'"
        >
          <div class="flex items-center gap-2">
            <UIcon
              :name="item.available ? 'i-heroicons-check-circle' : 'i-heroicons-lock-closed'"
              class="w-4 h-4 flex-shrink-0"
              :class="item.available ? 'text-primary-500' : 'text-gray-400'"
            />
            <span class="font-medium text-sm">{{ CHANNEL_LABELS[item.type] ?? item.type }}</span>
            <UBadge
              :label="item.available ? '当前可用' : '暂未开通'"
              :color="item.available ? 'primary' : 'neutral'"
              variant="subtle"
              size="xs"
            />
            <span
              v-if="item.solvable.length > 0"
              class="text-xs text-gray-400 ml-auto"
            >
              可解决 {{ item.solvable.length }} 项
            </span>
          </div>

          <div class="pl-6 space-y-1 text-xs">
            <div v-if="item.solvable.length" class="flex gap-1.5 flex-wrap">
              <span class="text-gray-500 flex-shrink-0">{{ item.available ? '能解决：' : '若开通可补充：' }}</span>
              <span
                v-for="s in item.solvable"
                :key="s"
                class="text-gray-700 dark:text-gray-300"
              >{{ s }}</span>
            </div>
            <div v-if="item.unsolvable.length" class="flex gap-1.5 flex-wrap">
              <span class="text-gray-400 flex-shrink-0">不能解决：</span>
              <span
                v-for="u in item.unsolvable"
                :key="u"
                class="text-gray-400"
              >{{ u }}</span>
            </div>
          </div>
        </div>
      </div>
    </UCard>

  </div>
</template>

<script setup lang="ts">
import { z } from 'zod'
import type { ChannelPlanItem, InsufficientReason, ParseBriefResponse } from '../../types'
import { CHANNEL_LABELS } from '../../composables/useStrategyConstants'

definePageMeta({
  layout: 'default',
  title: '新建策略',
})

const schema = z.object({
  name: z.string().min(1, '策略名称不能为空').max(255, '策略名称不能超过255个字符'),
  subject: z.string().min(1, '研究主体不能为空'),
  analysis_goal: z.string().min(1, '分析目标不能为空'),
  constraints: z.string().optional(),
})

type FormState = z.output<typeof schema>

const strategiesApi = useStrategiesApi()

const parsing = ref(false)
const submitting = ref(false)
const parsedChannelPlan = ref<ChannelPlanItem[] | null>(null)
const platformVerdict = ref<ParseBriefResponse['platform_verdict'] | null>(null)
const platformNote = ref('')
const insufficientReason = ref<InsufficientReason>('')

const formState = reactive<FormState>({
  name: '',
  subject: '',
  analysis_goal: '',
  constraints: '',
})

const applyResult = (result: Partial<ParseBriefResponse>) => {
  if (result.strategy_name) formState.name = result.strategy_name
  if (result.subject) formState.subject = result.subject
  if (result.analysis_goal) formState.analysis_goal = result.analysis_goal
  if (result.constraints) formState.constraints = result.constraints
  if (result.channel_plan?.length) parsedChannelPlan.value = result.channel_plan
  if (result.platform_verdict) platformVerdict.value = result.platform_verdict
  platformNote.value = result.platform_note ?? ''
  insufficientReason.value = result.insufficient_reason ?? ''
}

const handleParseText = async (text: string) => {
  parsing.value = true
  try {
    const result = await strategiesApi.parseBriefText(text)
    applyResult(result)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    parsing.value = false
  }
}

const parseFile = async (file: File) => {
  parsing.value = true
  try {
    const result = await strategiesApi.parseBrief(file)
    applyResult(result)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    parsing.value = false
  }
}

const handleSubmit = async () => {
  submitting.value = true
  try {
    const result = await strategiesApi.createStrategy({
      name: formState.name.trim(),
      brand_brief: {
        subject: formState.subject.trim(),
        analysis_goal: formState.analysis_goal.trim(),
        ...(formState.constraints?.trim() && { constraints: formState.constraints.trim() }),
        ...(parsedChannelPlan.value && { channel_plan: parsedChannelPlan.value }),
      },
    })
    navigateTo(`/strategies/${result.id}`)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    submitting.value = false
  }
}
</script>
