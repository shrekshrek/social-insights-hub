<template>
  <div v-if="evidence && evidence.length > 0" class="mt-2">
    <button
      class="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 flex items-center gap-1 cursor-pointer"
      @click="expanded = !expanded"
    >
      <UIcon
        :name="expanded ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
        class="size-3"
      />
      数据论据（{{ evidence.length }}）
    </button>
    <div v-if="expanded" class="mt-1.5 space-y-1">
      <div
        v-for="(item, idx) in evidence"
        :key="idx"
        class="text-xs text-gray-600 dark:text-gray-400 flex items-start gap-1"
      >
        <UBadge
          v-if="item.type"
          color="neutral"
          variant="subtle"
          size="sm"
          class="shrink-0 mt-0.5"
        >
          {{ item.type }}
        </UBadge>
        <span>{{ item.description }}</span>
        <span v-if="item.source" class="text-gray-400 shrink-0">({{ item.source }})</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { StageEvidence } from '../types'
import { UBadge, UIcon } from '#components'

defineProps<{
  evidence?: StageEvidence[]
}>()

const expanded = ref(false)
</script>
