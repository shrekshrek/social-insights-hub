<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div>
      <div class="flex items-center gap-2 mb-2">
        <UButton variant="ghost" icon="i-heroicons-arrow-left" size="sm" to="/research-agent" />
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          新建研究
        </h1>
      </div>
      <p class="text-gray-600 dark:text-gray-400">
        输入研究主题，AI 将自动搜索相关资料并生成结构化分析
      </p>
    </div>

    <UCard>
      <form class="space-y-6" @submit.prevent="handleSubmit">
        <!-- 研究主题 -->
        <UFormField label="研究主题" required>
          <UTextarea
            v-model="form.query"
            placeholder="例如：中国新能源汽车市场2024年竞争格局分析"
            :rows="2"
            autoresize
            class="w-full"
          />
        </UFormField>

        <!-- 研究类型 -->
        <UFormField label="研究类型">
          <template #description>
            {{ selectedTypeDescription }}
          </template>
          <USelect
            v-model="form.research_type"
            :items="researchTypeItems"
            value-key="value"
            class="w-full"
          />
        </UFormField>

        <!-- 研究问题 -->
        <UFormField label="研究问题（可选）">
          <template #description>
            不填写则由 AI 自动生成研究问题
          </template>
          <div class="space-y-2">
            <div
              v-for="(_, index) in form.questions"
              :key="index"
              class="flex items-center gap-2"
            >
              <UInput
                v-model="form.questions[index]"
                :placeholder="`研究问题 ${index + 1}`"
                class="flex-1"
              />
              <UButton
                variant="ghost"
                color="error"
                icon="i-heroicons-x-mark"
                size="sm"
                @click="removeQuestion(index)"
              />
            </div>
            <UButton
              variant="outline"
              icon="i-heroicons-plus"
              size="sm"
              @click="addQuestion"
            >
              添加问题
            </UButton>
          </div>
        </UFormField>

        <!-- 提交 -->
        <div class="flex justify-end gap-3">
          <UButton variant="outline" to="/research-agent">
            取消
          </UButton>
          <UButton
            type="submit"
            :loading="submitting"
            :disabled="!form.query.trim()"
            icon="i-heroicons-magnifying-glass"
          >
            开始研究
          </UButton>
        </div>
      </form>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { RESEARCH_TYPE_OPTIONS } from '../../composables/useResearchAgent'
import type { ResearchType } from '../../types'

definePageMeta({ layout: 'default' })
useHead({ title: '新建研究 - 研究分析' })

const { createTask } = useResearchAgent()
const toast = useToast()
const router = useRouter()

const submitting = ref(false)

const form = reactive({
  query: '',
  research_type: 'industry_research' as ResearchType,
  questions: [] as string[],
})

const researchTypeItems = RESEARCH_TYPE_OPTIONS.map(opt => ({
  value: opt.value,
  label: opt.label,
}))

const selectedTypeDescription = computed(() => {
  const found = RESEARCH_TYPE_OPTIONS.find(opt => opt.value === form.research_type)
  return found?.description ?? ''
})

function addQuestion() {
  form.questions.push('')
}

function removeQuestion(index: number) {
  form.questions.splice(index, 1)
}

async function handleSubmit() {
  if (!form.query.trim()) return

  submitting.value = true
  try {
    const validQuestions = form.questions.filter(q => q.trim())
    const task = await createTask({
      query: form.query.trim(),
      research_type: form.research_type,
      research_questions: validQuestions.length > 0 ? validQuestions : undefined,
    })
    toast.add({ title: `研究任务 #${task.id} 已创建，后台执行中`, color: 'success' })
    router.push(`/research-agent/${task.id}`)
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    submitting.value = false
  }
}
</script>
