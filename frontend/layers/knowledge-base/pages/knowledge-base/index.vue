<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          市场知识库
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          上传研报、行业资料，AI 策略生成时自动引用
        </p>
      </div>
      <UButton icon="i-heroicons-arrow-up-tray" @click="showUploadModal = true">
        上传文档
      </UButton>
    </div>

    <!-- 文档列表 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">文档列表</h2>
          <div class="flex items-center gap-2">
            <USelect v-model="workspaceFilter" :items="workspaceOptions" class="w-32" />
            <UButton
              variant="outline"
              icon="i-heroicons-arrow-path"
              :loading="loading"
              @click="refresh"
            >
              刷新
            </UButton>
          </div>
        </div>
      </template>

      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8 text-gray-500">加载文档列表中...</div>
        </template>

        <div v-if="loading" class="text-center py-8 text-gray-500">
          加载中...
        </div>
        <div v-else-if="!documents.length" class="text-center py-12">
          <UIcon name="i-heroicons-document-text" class="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p class="text-gray-500">暂无文档，点击上方按钮上传</p>
        </div>
        <div v-else class="divide-y divide-gray-100 dark:divide-gray-800">
          <div
            v-for="doc in documents"
            :key="doc.id"
            class="flex items-center justify-between py-4 px-2"
          >
            <div class="flex items-center gap-3 min-w-0">
              <UIcon name="i-heroicons-document-text" class="w-5 h-5 text-gray-400 shrink-0" />
              <div class="min-w-0">
                <p class="font-medium text-gray-900 dark:text-white truncate">{{ doc.title }}</p>
                <p class="text-sm text-gray-500">
                  {{ doc.filename }} · {{ formatFileSize(doc.file_size) }}
                  <span v-if="doc.chunk_count > 0"> · {{ doc.chunk_count }} 段</span>
                  <span v-if="doc.workspace_id === null" class="ml-1 text-blue-500">公开</span>
                  <span v-else class="ml-1 text-gray-400">私有</span>
                </p>
              </div>
            </div>
            <div class="flex items-center gap-3 shrink-0">
              <UBadge :color="statusColor(doc.processing_status)" variant="subtle">
                {{ statusLabel(doc.processing_status) }}
              </UBadge>
              <UButton
                variant="ghost"
                color="error"
                icon="i-heroicons-trash"
                size="sm"
                :loading="deletingId === doc.id"
                @click="handleDelete(doc)"
              />
            </div>
          </div>
        </div>
      </ClientOnly>

      <template #footer>
        <ClientOnly>
          <div v-if="total > pageSize" class="flex justify-center">
            <UPagination v-model:page="page" :total="total" :page-size="pageSize" />
          </div>
        </ClientOnly>
      </template>
    </UCard>

    <!-- 上传弹窗 -->
    <UModal v-model:open="showUploadModal" title="上传文档">
      <template #body>
        <div class="space-y-4">
          <UFormField label="文档标题（可选）">
            <UInput v-model="uploadForm.title" placeholder="留空则使用文件名" />
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

          <UFormField label="可见范围">
            <USelect v-model="uploadForm.isPublic" :items="visibilityOptions" />
          </UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="outline" @click="showUploadModal = false">取消</UButton>
          <UButton
            :loading="uploading"
            :disabled="!uploadForm.file"
            @click="handleUpload"
          >
            上传
          </UButton>
        </div>
      </template>
    </UModal>

    <!-- 删除确认弹窗 -->
    <UModal v-model:open="showDeleteModal" title="确认删除">
      <template #body>
        <p class="text-gray-700 dark:text-gray-300">
          确定要删除文档「{{ deletingDoc?.title }}」吗？此操作不可撤销。
        </p>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <UButton variant="outline" @click="showDeleteModal = false">取消</UButton>
          <UButton color="error" :loading="!!deletingId" @click="confirmDelete">删除</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>

<script setup lang="ts">
import type { KnowledgeDocument } from '../../types'

definePageMeta({ layout: 'default' })
useHead({ title: '市场知识库' })

const { listDocuments, uploadDocument, deleteDocument, statusLabel, statusColor, formatFileSize } = useKnowledgeBase()
const toast = useToast()

// 列表状态
const documents = ref<KnowledgeDocument[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const workspaceFilter = ref<'all' | 'public' | 'private'>('all')

const workspaceOptions = [
  { label: '全部', value: 'all' },
  { label: '公开', value: 'public' },
  { label: '私有', value: 'private' },
]

async function refresh() {
  loading.value = true
  try {
    const params: { page: number; page_size: number; workspace?: 'public' | 'private' } = {
      page: page.value,
      page_size: pageSize,
    }
    if (workspaceFilter.value !== 'all') params.workspace = workspaceFilter.value
    const res = await listDocuments(params)
    documents.value = res.items
    total.value = res.total
  } catch {
    toast.add({ title: '加载失败', color: 'error' })
  } finally {
    loading.value = false
  }
}

watch([page, workspaceFilter], refresh)
onMounted(refresh)

// 上传
const showUploadModal = ref(false)
const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadForm = reactive<{ title: string; file: File | null; isPublic: boolean }>({
  title: '',
  file: null,
  isPublic: false,
})

const visibilityOptions = [
  { label: '私有（仅自己可用）', value: false },
  { label: '公开（所有用户可用）', value: true },
]

function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  uploadForm.file = input.files?.[0] ?? null
}

async function handleUpload() {
  if (!uploadForm.file) return
  uploading.value = true
  try {
    await uploadDocument(uploadForm.file, uploadForm.title || undefined, undefined, uploadForm.isPublic)
    toast.add({ title: '上传成功，后台处理中', color: 'success' })
    showUploadModal.value = false
    uploadForm.title = ''
    uploadForm.file = null
    if (fileInputRef.value) fileInputRef.value.value = ''
    await refresh()
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '上传失败'
    toast.add({ title: msg, color: 'error' })
  } finally {
    uploading.value = false
  }
}

// 删除
const showDeleteModal = ref(false)
const deletingDoc = ref<KnowledgeDocument | null>(null)
const deletingId = ref<number | null>(null)

function handleDelete(doc: KnowledgeDocument) {
  deletingDoc.value = doc
  showDeleteModal.value = true
}

async function confirmDelete() {
  if (!deletingDoc.value) return
  deletingId.value = deletingDoc.value.id
  try {
    await deleteDocument(deletingDoc.value.id)
    toast.add({ title: '删除成功', color: 'success' })
    showDeleteModal.value = false
    deletingDoc.value = null
    await refresh()
  } catch {
    toast.add({ title: '删除失败', color: 'error' })
  } finally {
    deletingId.value = null
  }
}
</script>
