<script setup lang="ts">
import type { SpamDistribution, SpamCountBreakdown } from '../../types'

const props = withDefaults(defineProps<{
  /** 4 维模式（实体/观点） */
  spamDistribution?: SpamDistribution | null
  /** 2 维模式（IPA/竞品/时间） */
  spamBreakdown?: SpamCountBreakdown | null
  /** 是否显示文字标签 */
  showLabels?: boolean
  /** 尺寸 */
  size?: 'xs' | 'sm'
}>(), {
  spamDistribution: undefined,
  spamBreakdown: undefined,
  showLabels: true,
  size: 'sm',
})

/** 统一计算推广/有机数量 */
const counts = computed(() => {
  if (props.spamDistribution) {
    return {
      promo: props.spamDistribution.high_spam.total,
      organic: props.spamDistribution.low_spam.total,
      mode: 'full' as const,
    }
  }
  if (props.spamBreakdown) {
    return {
      promo: props.spamBreakdown.high,
      organic: props.spamBreakdown.low,
      mode: 'simple' as const,
    }
  }
  return null
})

/** 总数 */
const total = computed(() => {
  if (!counts.value) return 0
  return counts.value.promo + counts.value.organic
})

/** 推广占比 (0-100) */
const promoPercent = computed(() => {
  if (total.value === 0) return 0
  return (counts.value!.promo / total.value) * 100
})

/** 是否可见 */
const visible = computed(() => total.value > 0)

/** 是否为 4 维模式（有 post/comment 明细） */
const hasDetail = computed(() => counts.value?.mode === 'full' && props.spamDistribution != null)

/** 条形高度 class */
const barHeight = computed(() => props.size === 'xs' ? 'h-1.5' : 'h-2')
</script>

<template>
  <div v-if="visible" class="inline-flex items-center gap-1.5 text-xs">
    <!-- 4 维模式：带 Popover -->
    <UPopover v-if="hasDetail" :popper="{ placement: 'bottom-start' }">
      <div class="flex items-center gap-1.5 cursor-pointer">
        <!-- 比例条 -->
        <div :class="['flex rounded-full overflow-hidden w-16', barHeight]">
          <div
            class="bg-orange-400 dark:bg-orange-500 transition-all"
            :style="{ width: `${promoPercent}%` }"
          />
          <div
            class="bg-green-400 dark:bg-green-500 flex-1"
          />
        </div>
        <!-- 标签 -->
        <template v-if="showLabels">
          <span class="text-orange-600 dark:text-orange-400">{{ counts!.promo }}</span>
          <span class="text-gray-300 dark:text-gray-600">/</span>
          <span class="text-green-600 dark:text-green-400">{{ counts!.organic }}</span>
        </template>
      </div>

      <template #content>
        <div class="p-3 w-56 text-xs">
          <div class="font-medium text-sm mb-2 text-gray-900 dark:text-gray-100">广告分布明细</div>
          <div class="space-y-1.5">
            <div class="flex items-center justify-between">
              <span class="text-orange-600 dark:text-orange-400">推广 ({{ spamDistribution!.high_spam.total }})</span>
              <span class="text-gray-500 dark:text-gray-400">
                原文 {{ spamDistribution!.high_spam.post }} / 评论 {{ spamDistribution!.high_spam.comment }}
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-green-600 dark:text-green-400">有机 ({{ spamDistribution!.low_spam.total }})</span>
              <span class="text-gray-500 dark:text-gray-400">
                原文 {{ spamDistribution!.low_spam.post }} / 评论 {{ spamDistribution!.low_spam.comment }}
              </span>
            </div>
          </div>
        </div>
      </template>
    </UPopover>

    <!-- 2 维模式：无 Popover -->
    <template v-else>
      <div :class="['flex rounded-full overflow-hidden w-16', barHeight]">
        <div
          class="bg-orange-400 dark:bg-orange-500 transition-all"
          :style="{ width: `${promoPercent}%` }"
        />
        <div
          class="bg-green-400 dark:bg-green-500 flex-1"
        />
      </div>
      <template v-if="showLabels">
        <span class="text-orange-600 dark:text-orange-400">{{ counts!.promo }}</span>
        <span class="text-gray-300 dark:text-gray-600">/</span>
        <span class="text-green-600 dark:text-green-400">{{ counts!.organic }}</span>
      </template>
    </template>
  </div>
</template>
