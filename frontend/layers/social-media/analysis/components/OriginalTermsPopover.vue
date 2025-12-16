<script setup lang="ts">
import type { OriginalTerm } from '../types'

const props = withDefaults(defineProps<{
  text: string
  originalTerms?: OriginalTerm[]
  maxItems?: number
  placement?: string
  badgeColor?: 'neutral' | 'primary' | 'success' | 'warning' | 'error' | 'info'
}>(), {
  originalTerms: undefined,
  maxItems: 15,
  placement: 'bottom-start',
  badgeColor: 'neutral',
})

const hasOriginals = computed(() => Array.isArray(props.originalTerms) && props.originalTerms.length > 0)
const originalsCount = computed(() => props.originalTerms?.length || 0)
const displayTerms = computed(() => (props.originalTerms || []).slice(0, props.maxItems))
</script>

<template>
  <UPopover
    v-if="hasOriginals"
    :popper="{ placement }"
  >
    <span class="cursor-pointer underline decoration-dotted underline-offset-2">
      {{ text }}
      <UBadge :color="badgeColor" variant="subtle" size="xs" class="ml-1">
        {{ originalsCount }}
      </UBadge>
    </span>

    <template #content>
      <div class="p-3 w-72">
        <div class="font-medium text-sm mb-2 text-gray-900 dark:text-gray-100">
          {{ text }}
        </div>
        <div class="text-xs text-gray-500 mb-2">
          包含 {{ originalsCount }} 个原始观点：
        </div>
        <div class="space-y-1 text-xs text-gray-700 dark:text-gray-300">
          <div
            v-for="(t, idx) in displayTerms"
            :key="idx"
          >
            • {{ t.text }} ({{ t.count }})
          </div>
          <div
            v-if="originalsCount > maxItems"
            class="text-gray-400"
          >
            ... 等共 {{ originalsCount }} 个
          </div>
        </div>
      </div>
    </template>
  </UPopover>

  <span v-else>
    {{ text }}
  </span>
</template>


