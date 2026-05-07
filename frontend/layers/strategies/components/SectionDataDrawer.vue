<template>
  <div class="mt-3 pt-2 border-t border-dashed border-gray-200 dark:border-gray-700">
    <button
      class="text-xs text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 flex items-center gap-1.5 cursor-pointer transition-colors"
      :disabled="totalCount === 0"
      :class="{ 'opacity-50 cursor-not-allowed': totalCount === 0 }"
      @click="open = true"
    >
      <UIcon name="i-heroicons-circle-stack" class="size-3.5" />
      <span>本节使用了 {{ summaryLabel }}</span>
      <UIcon v-if="totalCount > 0" name="i-heroicons-arrow-up-right" class="size-3" />
    </button>

    <UModal v-model:open="open" :title="title">
      <template #content>
        <UCard>
          <template #header>
            <div class="flex items-center justify-between">
              <div>
                <h3 class="text-base font-semibold">{{ title }}</h3>
                <p class="text-xs text-gray-500 mt-0.5">
                  本节生成时 prompt 中实际注入的上游数据。点击对应条目可跳到原始切片。
                </p>
              </div>
              <UButton variant="ghost" size="xs" icon="i-heroicons-x-mark" @click="open = false" />
            </div>
          </template>

          <div class="space-y-4">
            <!-- 社媒切片 -->
            <section v-if="chainInputs.social_slices.length > 0">
              <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1.5">
                <UIcon name="i-heroicons-chat-bubble-left-right" class="size-4 text-blue-500" />
                社媒切片（{{ chainInputs.social_slices.length }}）
              </h4>
              <ul class="space-y-1.5">
                <li
                  v-for="(s, idx) in chainInputs.social_slices"
                  :key="`social-${s.id}`"
                  class="text-sm flex items-center gap-2 p-2 rounded bg-gray-50 dark:bg-gray-800"
                >
                  <span class="text-xs text-gray-400 shrink-0">#{{ idx }}</span>
                  <NuxtLink
                    v-if="s.monitor_id"
                    :to="`/social-media/monitors/${s.monitor_id}/analysis?slice_id=${s.id}`"
                    class="text-primary-600 dark:text-primary-400 hover:underline truncate"
                  >
                    {{ s.name || `切片 ${s.id}` }}
                  </NuxtLink>
                  <span v-else class="truncate">{{ s.name || `切片 ${s.id}` }}</span>
                  <span class="text-xs text-gray-400 ml-auto shrink-0">id: {{ s.id }}</span>
                </li>
              </ul>
            </section>

            <!-- 新闻切片 -->
            <section v-if="chainInputs.news_slices.length > 0">
              <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1.5">
                <UIcon name="i-heroicons-newspaper" class="size-4 text-amber-500" />
                新闻切片（{{ chainInputs.news_slices.length }}）
              </h4>
              <ul class="space-y-1.5">
                <li
                  v-for="(s, idx) in chainInputs.news_slices"
                  :key="`news-${s.id}`"
                  class="text-sm flex items-center gap-2 p-2 rounded bg-gray-50 dark:bg-gray-800"
                >
                  <span class="text-xs text-gray-400 shrink-0">#{{ idx }}</span>
                  <NuxtLink
                    :to="`/news-media/slices/${s.id}`"
                    class="text-primary-600 dark:text-primary-400 hover:underline truncate"
                  >
                    {{ s.name || `新闻切片 ${s.id}` }}
                  </NuxtLink>
                  <span class="text-xs text-gray-400 ml-auto shrink-0">id: {{ s.id }}</span>
                </li>
              </ul>
            </section>

            <!-- 行业研究 -->
            <section v-if="chainInputs.research_findings.length > 0">
              <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1.5">
                <UIcon name="i-heroicons-academic-cap" class="size-4 text-emerald-500" />
                行业研究（{{ chainInputs.research_findings.length }}）
              </h4>
              <ul class="space-y-1.5">
                <li
                  v-for="r in chainInputs.research_findings"
                  :key="`research-${r.id}`"
                  class="text-sm flex items-center gap-2 p-2 rounded bg-gray-50 dark:bg-gray-800"
                >
                  <UBadge color="success" variant="subtle" size="xs">industry</UBadge>
                  <span>研究任务 #{{ r.id }}</span>
                </li>
              </ul>
            </section>

            <!-- 创意参考 -->
            <section v-if="chainInputs.creative_references.length > 0">
              <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1.5">
                <UIcon name="i-heroicons-light-bulb" class="size-4 text-purple-500" />
                创意参考（{{ chainInputs.creative_references.length }}）
              </h4>
              <ul class="space-y-1.5">
                <li
                  v-for="r in chainInputs.creative_references"
                  :key="`creative-${r.id}`"
                  class="text-sm flex items-center gap-2 p-2 rounded bg-gray-50 dark:bg-gray-800"
                >
                  <UBadge color="warning" variant="subtle" size="xs">creative</UBadge>
                  <span>研究任务 #{{ r.id }}</span>
                </li>
              </ul>
            </section>

            <p class="text-xs text-gray-400 leading-relaxed pt-2 border-t border-gray-100 dark:border-gray-800">
              说明：以上为本节生成时实际喂给 LLM 的输入清单（不含 LLM 是否真的引用每一条）。
              如需精确到具体 evidence 的来源，请展开各条目下的"数据论据"。
            </p>
          </div>
        </UCard>
      </template>
    </UModal>
  </div>
</template>

<script setup lang="ts">
import type { ChainInputs } from '../types'
import { UModal, UCard, UButton, UIcon, UBadge } from '#components'

const props = defineProps<{
  chainInputs: ChainInputs | null | undefined
  /** 弹窗标题，默认"原始数据来源" */
  title?: string
}>()

const open = ref(false)

const chainInputs = computed<ChainInputs>(() => ({
  social_slices: props.chainInputs?.social_slices ?? [],
  news_slices: props.chainInputs?.news_slices ?? [],
  research_findings: props.chainInputs?.research_findings ?? [],
  creative_references: props.chainInputs?.creative_references ?? [],
}))

const totalCount = computed(() =>
  chainInputs.value.social_slices.length
  + chainInputs.value.news_slices.length
  + chainInputs.value.research_findings.length
  + chainInputs.value.creative_references.length,
)

const summaryLabel = computed(() => {
  const parts: string[] = []
  if (chainInputs.value.social_slices.length > 0)
    parts.push(`${chainInputs.value.social_slices.length} 条社媒切片`)
  if (chainInputs.value.news_slices.length > 0)
    parts.push(`${chainInputs.value.news_slices.length} 条新闻切片`)
  if (chainInputs.value.research_findings.length > 0)
    parts.push(`${chainInputs.value.research_findings.length} 个行业研究`)
  if (chainInputs.value.creative_references.length > 0)
    parts.push(`${chainInputs.value.creative_references.length} 个创意参考`)
  if (parts.length === 0) return '无可用上游数据'
  return parts.join(' · ') + ' · 查看原始数据'
})

const title = computed(() => props.title || '本节原始数据来源')
</script>
