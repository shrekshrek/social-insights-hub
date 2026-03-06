<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="max-w-3xl mx-auto space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          to="/strategies"
        />
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">新建策略</h1>
          <p class="text-sm text-gray-500 mt-0.5">填写品牌基本信息，AI 将在下一步协助规划监测方案</p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <UButton variant="outline" :disabled="submitting" to="/strategies">
          取消
        </UButton>
        <UButton :loading="submitting" :disabled="!canSubmit" @click="handleSubmit">
          创建
        </UButton>
      </div>
    </div>

    <UCard>
      <div class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
          <UFormField label="策略名称" required>
            <UInput
              v-model="form.name"
              placeholder="例如: 大魔王世界杯营销策略"
              class="w-full"
            />
          </UFormField>

          <UFormField label="品牌 / 产品" required>
            <UInput
              v-model="brief.brand_name"
              placeholder="例如: 大魔王素毛肚"
              class="w-full"
            />
          </UFormField>
        </div>

        <UFormField label="分析目标" required>
          <UTextarea
            v-model="brief.analysis_goal"
            placeholder="简述你想通过社媒数据解决的问题，例如:&#10;借世界杯营销，了解消费者对看球零食的讨论热点，找到品牌切入机会"
            :rows="3"
            class="w-full"
          />
        </UFormField>

        <UFormField label="补充说明">
          <UTextarea
            v-model="brief.constraints"
            placeholder="可选，例如: 行业背景、竞品信息、时间范围、特殊关注点等（不确定的部分可留给 AI 咨询阶段补充）"
            :rows="2"
            class="w-full"
          />
        </UFormField>
      </div>

      <p class="text-xs text-gray-400 mt-4">
        创建后进入 AI 咨询流程，AI 会根据目标追问细节并规划监测方案，无需提前准备所有信息。
      </p>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import type { BrandBrief } from '../../types'

definePageMeta({
  title: '新建策略',
})

const strategiesApi = useStrategies()

const submitting = ref(false)
const form = ref({ name: '' })
const brief = ref<Partial<BrandBrief>>({
  brand_name: '',
  analysis_goal: '',
  constraints: '',
})

const canSubmit = computed(() => {
  return (
    form.value.name.trim().length > 0
    && (brief.value.brand_name?.trim().length ?? 0) > 0
    && (brief.value.analysis_goal?.trim().length ?? 0) > 0
  )
})

const handleSubmit = async () => {
  if (!canSubmit.value) return

  submitting.value = true
  try {
    const brandBrief: BrandBrief = {
      brand_name: brief.value.brand_name!.trim(),
      analysis_goal: brief.value.analysis_goal!.trim(),
      ...(brief.value.constraints?.trim() && { constraints: brief.value.constraints.trim() }),
    }

    const result = await strategiesApi.createStrategy({
      name: form.value.name.trim(),
      brand_brief: brandBrief,
    })
    navigateTo(`/strategies/${result.id}`)
  } catch {
    // 错误已由 useApi 自动处理
  } finally {
    submitting.value = false
  }
}
</script>
