<template>
  <div class="max-w-2xl mx-auto">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        上传文档
      </h1>
      <p class="text-gray-600 dark:text-gray-400 mt-1">
        上传研报、行业资料到知识库，AI 策略生成时可自动引用
      </p>
    </div>

    <!-- 上传表单 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">文档信息</h2>
      </template>

      <template #body>
        <div class="space-y-6">
          <UFormField label="文档标题（可选）">
            <UInput v-model="form.title" placeholder="留空则使用文件名" />
            <p class="text-xs text-gray-400 mt-1">为文档设置一个易于识别的标题</p>
          </UFormField>

          <UFormField label="选择文件">
            <input
              ref="fileInputRef"
              type="file"
              accept=".pdf,.docx,.txt,.md"
              class="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100"
              @change="handleFileChange"
            >
            <p class="text-xs text-gray-400 mt-1">支持 PDF、DOCX、TXT、MD，最大 50 MB</p>
          </UFormField>

          <div class="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
            <div class="flex gap-2">
              <UIcon name="i-heroicons-information-circle" class="w-5 h-5 text-yellow-600 dark:text-yellow-400 shrink-0" />
              <div class="text-sm text-yellow-800 dark:text-yellow-200">
                <p class="font-medium">处理说明</p>
                <p class="mt-1">文档上传后将自动进行解析、分块和向量化处理，处理完成后即可用于 RAG 检索和策略生成。</p>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template #footer>
        <div class="flex justify-end gap-3">
          <UButton variant="outline" to="/knowledge-base">
            取消
          </UButton>
          <UButton
            :loading="uploading"
            :disabled="!form.file"
            @click="handleUpload"
          >
            上传
          </UButton>
        </div>
      </template>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { UCard, UButton, UFormField, UIcon } from '#components'

definePageMeta({ layout: 'default' })
useHead({ title: '上传文档' })

const { uploadDocument } = useKnowledgeBaseApi()
const toast = useToast()

const fileInputRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

const form = reactive<{
  title: string
  file: File | null
}>({
  title: '',
  file: null,
})

function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  form.file = input.files?.[0] ?? null
}

async function handleUpload() {
  if (!form.file) return

  uploading.value = true
  try {
    await uploadDocument(form.file, form.title || undefined)
    toast.add({ title: '上传成功，后台处理中', color: 'success' })
    // 延迟跳转，让用户看到成功提示
    setTimeout(() => {
      navigateTo('/knowledge-base')
    }, 1500)
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    uploading.value = false
  }
}
</script>
