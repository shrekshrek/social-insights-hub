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
      <UButton icon="i-heroicons-arrow-up-tray" to="/knowledge-base/upload">
        上传文档
      </UButton>
    </div>

    <!-- 文档列表 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">文档列表</h2>
          <div class="flex items-center gap-2">
            <USelect v-model="sourceTypeFilter" :items="sourceTypeOptions" class="w-40" />
            <UButton
              variant="outline"
              icon="i-heroicons-arrow-path"
              @click="handleRefresh"
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
                  {{ doc.file_name }} · {{ formatFileSize(doc.chunk_count * 500) }}
                  <span v-if="doc.chunk_count > 0"> · {{ doc.chunk_count }} 段</span>
                  <span v-if="doc.source_type !== 'upload'" class="ml-1 text-blue-500">
                    {{ doc.source_type.toUpperCase() }}
                  </span>
                </p>
              </div>
            </div>

            <div class="flex items-center gap-3 shrink-0">
              <UBadge :color="statusColor(doc.processing_status)" variant="subtle">
                {{ statusLabel(doc.processing_status) }}
              </UBadge>
              <UButton
                v-if="doc.workspace_id !== null"
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
    </UCard>

    <!-- 爬虫状态面板 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <UIcon name="i-heroicons-cloud-arrow-down" class="w-4 h-4" />
            数据源状态
          </h2>
          <UButton variant="ghost" size="sm" icon="i-heroicons-arrow-path" @click="() => refreshCrawler()" />
        </div>
      </template>

      <div>
        <ClientOnly>
          <template #fallback>
            <div class="text-center py-4 text-gray-500">加载状态中...</div>
          </template>

          <div v-if="loadingCrawler" class="text-center py-4 text-gray-500">
            加载中...
          </div>

          <table v-else class="w-full">
            <thead class="text-xs text-gray-500 bg-gray-50 dark:bg-gray-900">
              <tr>
                <th class="text-left py-2 px-4">数据源</th>
                <th class="text-right py-2 px-4">总数</th>
                <th class="text-right py-2 px-4">就绪</th>
                <th class="text-right py-2 px-4">失败</th>
                <th class="text-right py-2 px-4">最后更新</th>
                <th class="text-center py-2 px-4">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in crawlerStatus" :key="item.source_type" class="border-b border-gray-200 dark:border-gray-800">
                <td class="py-3 px-4">
                  <span class="font-medium">{{ sourceTypeLabel(item.source_type) }}</span>
                </td>
                <td class="text-right py-3 px-4">{{ item.total_docs }}</td>
                <td class="text-right py-3 px-4 text-green-600">{{ item.ready_docs }}</td>
                <td class="text-right py-3 px-4 text-red-600">{{ item.failed_docs }}</td>
                <td class="text-right py-3 px-4">
                  {{ item.last_crawled_at ? formatDate(item.last_crawled_at) : '-' }}
                </td>
                <td class="text-center py-3 px-4">
                  <UButton
                    variant="ghost"
                    size="xs"
                    :loading="runningCrawler === item.source_type"
                    @click="handleRunCrawler(item.source_type)"
                  >
                    触发
                  </UButton>
                </td>
              </tr>
            </tbody>
          </table>
        </ClientOnly>
      </div>
    </UCard>

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
import { ref, computed, watch } from 'vue'
import type { KnowledgeDocument } from '../../types'
import { PERMISSIONS } from '~/config/permissions'
import type { Permission } from '~/types/permissions'
import { UCard, UButton, USelect, UBadge, UModal, UIcon } from '#components'

definePageMeta({ layout: 'default' })
useHead({ title: '市场知识库' })

const { getDocuments, deleteDocument, getCrawlerStatus, runCrawler, sourceTypeLabel, statusColor, statusLabel, formatFileSize } = useKnowledgeBase()
const toast = useToast()
const { hasPermission } = usePermissions()

// 列表状态
const sourceTypeFilter = ref<'all' | 'upload' | 'cnnic' | 'nbs' | 'govsite'>('all')

const sourceTypeOptions = [
  { label: '全部', value: 'all' },
  { label: '上传', value: 'upload' },
  { label: 'CNNIC 统计报告', value: 'cnnic' },
  { label: 'CNNIC 专题研究', value: 'cnnic_research' },
  { label: 'NBS', value: 'nbs' },
  { label: 'gov.cn', value: 'govsite' },
]

// 使用 useApiData 获取文档列表
const params = computed(() => ({
  page: 1,
  page_size: 20,
  source_type: sourceTypeFilter.value === 'all' ? undefined : sourceTypeFilter.value,
}))

const { data: documentsData, pending: loading, refresh } = getDocuments(params)

const documents = computed(() => documentsData.value?.items || [])

// 爬虫状态面板
const showCrawlerPanel = ref(true)

const { data: crawlerData, pending: loadingCrawler, refresh: refreshCrawler } = getCrawlerStatus()

const crawlerStatus = computed(() => crawlerData.value?.items || [])
const runningCrawler = ref<string | null>(null)

// 删除
const showDeleteModal = ref(false)
const deletingDoc = ref<KnowledgeDocument | null>(null)
const deletingId = ref<number | null>(null)

// 格式化日期
function formatDate(dateStr: string): string {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// 刷新列表
function handleRefresh() {
  refresh()
}

// 删除
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
    refresh()
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    deletingId.value = null
  }
}

// 触发爬虫
async function handleRunCrawler(sourceType: string) {
  if (!hasPermission(PERMISSIONS.KB_WRITE as Permission)) {
    toast.add({ title: '无操作权限', color: 'error' })
    return
  }
  runningCrawler.value = sourceType
  try {
    const res = await runCrawler(sourceType)
    toast.add({ title: res.message || '已派发爬取任务', color: 'success' })
    refreshCrawler()
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    runningCrawler.value = null
  }
}

// 页面展开时刷新爬虫状态
watch(showCrawlerPanel, (val) => {
  if (val) refreshCrawler()
})
</script>
