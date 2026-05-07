<template>
  <div v-if="provenance" class="flex items-center gap-1.5 flex-wrap text-xs">
    <!-- 主数据源 chip：有 chain_inputs 时点击展开详情，否则纯标签 -->
    <UBadge
      :color="primaryColor"
      variant="subtle"
      size="sm"
      :class="[
        'flex items-center',
        canDrillDown ? 'cursor-pointer hover:opacity-80 transition-opacity' : '',
      ]"
      @click="canDrillDown && (open = true)"
    >
      <UIcon :name="primaryIcon" class="size-3 mr-0.5" />
      {{ primaryLabel }}
      <UIcon
        v-if="canDrillDown"
        name="i-heroicons-arrow-up-right"
        class="size-2.5 ml-0.5 opacity-70"
      />
    </UBadge>
    <!-- 行业研究视角 chip：与主数据源共用同一个详情 modal -->
    <UBadge
      v-if="provenance.research?.industry_research"
      color="neutral"
      variant="subtle"
      size="sm"
      :class="[
        'flex items-center',
        canDrillDown ? 'cursor-pointer hover:opacity-80 transition-opacity' : '',
      ]"
      @click="canDrillDown && (open = true)"
    >
      <UIcon name="i-heroicons-building-library" class="size-3 mr-0.5" />
      行业研究
    </UBadge>
    <!-- 创意研究视角 chip：仅当本节注入了创意参考时显示 -->
    <UBadge
      v-if="chainInputs.creative_references.length > 0"
      color="neutral"
      variant="subtle"
      size="sm"
      :class="[
        'flex items-center',
        canDrillDown ? 'cursor-pointer hover:opacity-80 transition-opacity' : '',
      ]"
      @click="canDrillDown && (open = true)"
    >
      <UIcon name="i-heroicons-light-bulb" class="size-3 mr-0.5" />
      创意研究
    </UBadge>

    <!-- 详情 modal：当 chainInputs 有数据时由 chip 点击触发 -->
    <UModal v-if="canDrillDown" v-model:open="open" :title="modalTitle">
      <template #content>
        <UCard>
          <template #header>
            <div class="flex items-center justify-between">
              <div>
                <h3 class="text-base font-semibold">{{ modalTitle }}</h3>
                <p class="text-xs text-gray-500 mt-0.5">
                  本节生成时 prompt 中实际注入的上游数据。点击对应条目可跳到原始切片。
                </p>
              </div>
              <UButton variant="ghost" size="xs" icon="i-heroicons-x-mark" @click="open = false" />
            </div>
          </template>

          <div class="space-y-4">
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
import type { ChainInputs, DataProvenance } from '../types'
import { UBadge, UButton, UIcon, UModal, UCard } from '#components'

const props = defineProps<{
  provenance: DataProvenance | null | undefined
  /** 可选：本节 chain_inputs，传入后 chip 变可点击，弹出详情 modal 列出每条切片/研究的 ID + 名称 */
  chainInputs?: ChainInputs | null
  /** modal 标题，默认 "原始数据来源" */
  modalTitle?: string
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

const canDrillDown = computed(() => totalCount.value > 0)

const modalTitle = computed(() => props.modalTitle || '原始数据来源')

const isSocial = computed(() => props.provenance?.primary?.channel === 'social_media')

const primaryColor = computed(() => (isSocial.value ? 'primary' : 'warning') as 'primary' | 'warning')

const primaryIcon = computed(() =>
  isSocial.value ? 'i-heroicons-chat-bubble-left-right' : 'i-heroicons-newspaper',
)

const primaryLabel = computed(() => {
  const p = props.provenance?.primary
  if (!p) return ''
  if (p.channel === 'social_media') {
    return `社媒主源 · ${p.social_media_slice_count} 切片`
  }
  return `新闻主源 · ${p.news_media_slice_count} 切片`
})
</script>
