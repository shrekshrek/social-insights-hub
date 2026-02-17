<script setup lang="ts">
import type { SpamDistribution } from '../../types'

const props = withDefaults(defineProps<{
  /** Spam 分布数据（4 维） */
  spamDistribution?: SpamDistribution | null
}>(), {
  spamDistribution: undefined,
})

/** 推广/有机数量 */
const promo = computed(() => props.spamDistribution?.high_spam.total ?? 0)
const organic = computed(() => props.spamDistribution?.low_spam.total ?? 0)
const total = computed(() => promo.value + organic.value)

/** 是否可见 */
const visible = computed(() => total.value > 0 && props.spamDistribution != null)
</script>

<template>
  <div v-if="visible" class="inline-flex items-center gap-1.5 text-xs">
    <!-- 推广明细 -->
    <span class="text-orange-600 dark:text-orange-400">推广 {{ promo }}</span>
    <span class="text-gray-400 dark:text-gray-500">(原{{ spamDistribution!.high_spam.post }}/评{{ spamDistribution!.high_spam.comment }})</span>

    <span class="text-gray-300 dark:text-gray-600 mx-0.5">/</span>

    <!-- 有机明细 -->
    <span class="text-green-600 dark:text-green-400">有机 {{ organic }}</span>
    <span class="text-gray-400 dark:text-gray-500">(原{{ spamDistribution!.low_spam.post }}/评{{ spamDistribution!.low_spam.comment }})</span>
  </div>
</template>
