<template>
  <div class="space-y-6">
    <!-- Big Idea -->
    <div>
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Big Idea</h4>
      <div class="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border-l-4 border-green-500 space-y-3">
        <UFormField label="创意概念">
          <UInput
            v-model="localData.big_idea.statement"
            placeholder="创意概念（一句话）"
            class="w-full"
          />
        </UFormField>
        <UFormField label="概念阐释">
          <UTextarea
            v-model="localData.big_idea.elaboration"
            :rows="3"
            placeholder="概念阐释（2-3句）"
            class="w-full"
          />
        </UFormField>
        <UFormField label="与核心矛盾的呼应">
          <UTextarea
            v-model="localData.big_idea.tension_echo"
            :rows="2"
            placeholder="这个创意如何回应核心社会矛盾"
            class="w-full"
          />
        </UFormField>
        <EvidenceEditList v-model="localData.big_idea.evidence" />
      </div>
    </div>

    <!-- Content Strategy -->
    <div>
      <h4 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">Content Strategy</h4>
      <div class="space-y-3">
        <div
          v-for="(pillar, idx) in localData.content_strategy.pillars"
          :key="idx"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg space-y-2"
        >
          <UFormField :label="`支柱 ${idx + 1} 名称`">
            <UInput
              v-model="pillar.name"
              placeholder="支柱名称"
              class="w-full"
            />
          </UFormField>
          <UFormField label="描述">
            <UTextarea
              v-model="pillar.description"
              :rows="2"
              placeholder="支柱描述和方向"
              class="w-full"
            />
          </UFormField>
          <div v-if="pillar.reference_examples?.length">
            <p class="text-xs font-medium text-gray-500 mb-1">参考案例</p>
            <div class="space-y-1">
              <UInput
                v-for="(_, eidx) in pillar.reference_examples"
                :key="eidx"
                v-model="pillar.reference_examples![eidx]"
                :placeholder="`案例 ${eidx + 1}`"
                class="w-full text-sm"
              />
            </div>
          </div>
        </div>
      </div>
      <EvidenceEditList v-model="localData.content_strategy.evidence" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BigIdeaResult } from '../types'
import { UInput, UTextarea, UFormField } from '#components'

const props = defineProps<{
  result: BigIdeaResult
}>()

const localData = ref<BigIdeaResult>(JSON.parse(JSON.stringify(props.result)))

defineExpose({
  getResult: () => JSON.parse(JSON.stringify(localData.value)),
})
</script>
