<script setup lang="ts">
import { z } from 'zod'

definePageMeta({
  layout: 'default',
})

const { createMonitor } = useNewsMonitors()
const router = useRouter()
const submitting = ref(false)

const schema = z.object({
  name: z.string().min(1, '项目名称不能为空').max(255, '项目名称不能超过255个字符'),
  description: z.string().optional(),
})

type FormSchema = z.output<typeof schema>

const formState = reactive<FormSchema>({
  name: '',
  description: '',
})

const handleBack = () => {
  if (window.history.length > 1) {
    router.back()
  } else {
    navigateTo('/news-media/monitors')
  }
}

const handleSubmit = async () => {
  submitting.value = true
  try {
    const result = await createMonitor({
      name: formState.name,
      description: formState.description || undefined,
    })

    await navigateTo(`/news-media/monitors/${result.id}`)
  } catch {
    // error already handled by apiRequest
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          @click="handleBack"
        />
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
            新建新闻监测项目
          </h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">
            创建一个新闻媒体数据监测项目
          </p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          variant="outline"
          :disabled="submitting"
          to="/news-media/monitors"
        >
          取消
        </UButton>
        <UButton
          :loading="submitting"
          @click="handleSubmit"
        >
          创建
        </UButton>
      </div>
    </div>

    <UCard>
      <template #header>
        <h2 class="text-base font-semibold">
          项目信息
        </h2>
      </template>

      <UForm
        :schema="schema"
        :state="formState"
      >
        <div class="grid grid-cols-1 gap-5">
          <UFormField
            label="项目名称"
            name="name"
            required
          >
            <UInput
              v-model="formState.name"
              placeholder="请输入项目名称"
              class="w-full"
            />
          </UFormField>

          <UFormField
            label="项目描述"
            name="description"
          >
            <UTextarea
              v-model="formState.description"
              placeholder="请输入项目描述"
              :rows="3"
              class="w-full"
            />
          </UFormField>
        </div>
      </UForm>
    </UCard>
  </div>
</template>
