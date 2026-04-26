<template>
  <UModal v-model:open="open" title="微调切片配置" description="调整切片的名称、主体品牌和竞品配置">
    <template #content>
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h3 class="text-lg font-semibold">微调切片配置</h3>
            <UButton variant="ghost" size="xs" icon="i-heroicons-x-mark" @click="open = false" />
          </div>
        </template>

        <div class="space-y-4">
          <div
            v-for="(adj, i) in adjustments"
            :key="i"
            class="p-3 border border-gray-200 dark:border-gray-700 rounded-lg space-y-2"
          >
            <div class="flex items-center gap-2">
              <UIcon name="i-heroicons-scissors" class="text-purple-500 shrink-0" />
              <span class="text-sm font-medium">切片 #{{ adj.slice_id }}</span>
            </div>

            <UFormField label="名称" size="sm">
              <UInput
                :model-value="adj.name || ''"
                size="sm"
                placeholder="切片名称"
                @update:model-value="(v: string) => updateField(i, 'name', v)"
              />
            </UFormField>

            <UFormField label="主体品牌" size="sm">
              <UInput
                :model-value="adj.subject || ''"
                size="sm"
                placeholder="主体品牌（留空为大盘分析）"
                @update:model-value="(v: string) => updateField(i, 'subject', v)"
              />
            </UFormField>

            <UFormField label="竞品" size="sm">
              <UInput
                :model-value="(adj.competitors || []).join(', ')"
                size="sm"
                placeholder="竞品列表（逗号分隔）"
                @update:model-value="(v: string) => updateCompetitors(i, v)"
              />
            </UFormField>
          </div>
        </div>

        <template #footer>
          <div class="flex justify-end gap-2">
            <UButton variant="outline" @click="open = false">取消</UButton>
            <UButton :loading="saving" @click="handleSave">保存</UButton>
          </div>
        </template>
      </UCard>
    </template>
  </UModal>
</template>

<script setup lang="ts">
import type { AdjustSliceItem, SliceSummary } from '../types'

const props = defineProps<{
  slices: SliceSummary[]
  saving: boolean
}>()

const emit = defineEmits<{
  save: [adjustments: AdjustSliceItem[]]
}>()

const open = defineModel<boolean>('open', { default: false })

const adjustments = ref<AdjustSliceItem[]>([])
const originalNames = ref<Record<number, string | null>>({})

// 仅社媒切片可微调；新闻切片调整需要重跑 insight chain，暂不支持
const adjustableSlices = computed(() => props.slices.filter(s => s.channel === 'social'))

// 当 modal 打开时，从 adjustableSlices 初始化 adjustments，记录原始名称
watch(open, (isOpen) => {
  if (isOpen) {
    const names: Record<number, string | null> = {}
    adjustments.value = adjustableSlices.value.map(s => {
      names[s.slice_id] = s.slice_name
      return {
        slice_id: s.slice_id,
        name: s.slice_name,
        subject: null,
        competitors: null,
      }
    })
    originalNames.value = names
  }
})

const updateField = (index: number, field: 'name' | 'subject', value: string) => {
  adjustments.value = adjustments.value.map((adj, i) =>
    i === index ? { ...adj, [field]: value || null } : adj,
  )
}

const updateCompetitors = (index: number, value: string) => {
  const competitors = value
    .split(/[,，、]/)
    .map(s => s.trim())
    .filter(Boolean)
  adjustments.value = adjustments.value.map((adj, i) =>
    i === index ? { ...adj, competitors: competitors.length ? competitors : null } : adj,
  )
}

const handleSave = () => {
  // 只发送有实际修改的项（名称与原始值不同 或 subject/competitors 被设置）
  const changed = adjustments.value.filter(adj => {
    const nameChanged = adj.name !== originalNames.value[adj.slice_id]
    return nameChanged || adj.subject !== null || adj.competitors !== null
  })
  if (changed.length > 0) {
    emit('save', changed)
  }
}
</script>
