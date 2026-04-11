<template>
  <div v-if="evidence && evidence.length > 0" class="mt-2">
    <p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">数据论据</p>
    <div class="space-y-1">
      <div
        v-for="(item, idx) in evidence"
        :key="idx"
        class="text-xs text-gray-600 dark:text-gray-400 flex items-start gap-1"
      >
        <UBadge
          v-if="item.type"
          color="neutral"
          variant="subtle"
          size="xs"
          class="shrink-0 mt-0.5"
        >
          {{ item.type }}
        </UBadge>
        <span>{{ item.description }}</span>
        <span v-if="item.source" class="text-gray-400">({{ item.source }})</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { StageEvidence } from '../types'
import { UBadge } from '#components'

defineProps<{
  evidence?: StageEvidence[]
}>()
</script>
