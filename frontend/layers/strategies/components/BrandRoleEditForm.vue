<template>
  <div class="space-y-6">
    <!-- Brand Social Role -->
    <div>
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Brand Social Role</h4>
      <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg space-y-3">
        <UFormField label="角色定义">
          <UInput
            v-model="localData.brand_social_role.statement"
            placeholder="品牌应扮演的角色（一句话）"
            class="w-full"
          />
        </UFormField>
        <UFormField label="角色阐释">
          <UTextarea
            v-model="localData.brand_social_role.elaboration"
            :rows="3"
            placeholder="角色阐释（2-3句）"
            class="w-full"
          />
        </UFormField>
        <EvidenceEditList v-model="localData.brand_social_role.evidence" />
      </div>
    </div>

    <!-- Social Strategy -->
    <div>
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Social Strategy</h4>
      <div class="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg space-y-3">
        <UFormField label="策略主张">
          <UInput
            v-model="localData.social_strategy.statement"
            placeholder="策略主张（一句话）"
            class="w-full"
          />
        </UFormField>
        <UFormField label="核心信息">
          <UInput
            v-model="localData.social_strategy.core_message"
            placeholder="核心沟通信息"
            class="w-full"
          />
        </UFormField>
        <UFormField label="传播节奏">
          <UInput
            v-model="localData.social_strategy.rhythm"
            placeholder="传播节奏建议"
            class="w-full"
          />
        </UFormField>
        <EvidenceEditList v-model="localData.social_strategy.evidence" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BrandRoleResult } from '../types'
import { UInput, UTextarea, UFormField } from '#components'

const props = defineProps<{
  result: BrandRoleResult
}>()

const localData = ref<BrandRoleResult>(JSON.parse(JSON.stringify(props.result)))

defineExpose({
  getResult: () => JSON.parse(JSON.stringify(localData.value)),
})
</script>
