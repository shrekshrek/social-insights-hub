<template>
  <div v-if="provenance" class="flex items-center gap-1.5 flex-wrap text-xs">
    <!-- 主数据源：显示渠道 + 切片数 -->
    <UBadge :color="primaryColor" variant="subtle" size="xs">
      <UIcon :name="primaryIcon" class="size-3 mr-0.5" />
      {{ primaryLabel }}
    </UBadge>
    <!-- 背景数据源：knowledge_base -->
    <UBadge
      v-if="provenance.background?.knowledge_base"
      color="neutral"
      variant="soft"
      size="xs"
    >
      <UIcon name="i-heroicons-book-open" class="size-3 mr-0.5" />
      知识库背景
    </UBadge>
  </div>
</template>

<script setup lang="ts">
import type { DataProvenance } from '../types'
import { UBadge, UIcon } from '#components'

const props = defineProps<{
  provenance: DataProvenance | null | undefined
}>()

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
