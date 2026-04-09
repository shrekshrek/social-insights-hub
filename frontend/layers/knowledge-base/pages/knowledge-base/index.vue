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
            <UButton
              v-if="selectedIds.size > 0"
              color="error"
              variant="outline"
              icon="i-heroicons-trash"
              @click="handleBatchDelete"
            >
              删除选中 ({{ selectedIds.size }})
            </UButton>
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
          <!-- 全选行 -->
          <div class="flex items-center gap-3 py-2 px-2 text-sm text-gray-500">
            <UCheckbox
              :model-value="selectedIds.size === documents.length && documents.length > 0"
              :indeterminate="selectedIds.size > 0 && selectedIds.size < documents.length"
              @update:model-value="toggleSelectAll"
            />
            <span>全选</span>
          </div>
          <div
            v-for="doc in documents"
            :key="doc.id"
            class="flex items-center justify-between py-4 px-2"
          >
            <div class="flex items-center gap-3 min-w-0">
              <UCheckbox
                :model-value="selectedIds.has(doc.id)"
                @update:model-value="toggleSelect(doc.id)"
              />
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
                v-if="doc.file_path && doc.processing_status === 'ready'"
                variant="ghost"
                icon="i-heroicons-eye"
                size="sm"
                :loading="viewingId === doc.id"
                @click="handleView(doc)"
              />
              <UButton
                v-if="doc.workspace_id !== null || hasPermission(PERMISSIONS.KB_DELETE as Permission)"
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

      <template v-if="total > 0" #footer>
        <ClientOnly>
          <template #fallback>
            <div class="flex justify-between items-center">
              <div class="h-4 bg-gray-200 rounded w-32 animate-pulse" />
              <div class="h-8 bg-gray-200 rounded w-64 animate-pulse" />
            </div>
          </template>
          <div class="flex justify-between items-center">
            <div class="text-sm text-gray-500 dark:text-gray-400">
              显示 {{ (currentPage - 1) * PAGE_SIZE + 1 }} 到
              {{ Math.min(currentPage * PAGE_SIZE, total) }} 共
              {{ total }} 条记录
            </div>
            <UPagination
              v-model:page="currentPage"
              :total="total"
              :items-per-page="PAGE_SIZE"
              :sibling-count="2"
              show-first
              show-last
              show-edges
            />
          </div>
        </ClientOnly>
      </template>
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

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { KnowledgeDocument } from '../../types'
import { PERMISSIONS } from '~/config/permissions'
import type { Permission } from '~/types/permissions'
import { UCard, UButton, USelect, UBadge, UIcon, UCheckbox, UPagination } from '#components'

definePageMeta({ layout: 'default' })
useHead({ title: '市场知识库' })

const { getDocuments, deleteDocument, deleteDocuments, viewDocument, getCrawlerStatus, runCrawler, sourceTypeLabel, statusColor, statusLabel, formatFileSize } = useKnowledgeBase()
const toast = useToast()
const { hasPermission } = usePermissions()

// 列表状态
const sourceTypeFilter = ref<'all' | 'upload' | 'cnnic' | 'nbs' | 'govsite'>('all')

const sourceTypeOptions = [
  { label: '全部', value: 'all' },
  { label: '上传', value: 'upload' },
  { label: 'CNNIC 报告库', value: 'cnnic' },
  { label: 'NBS', value: 'nbs' },
  { label: 'gov.cn', value: 'govsite' },
]

// 分页
const PAGE_SIZE = 20
const currentPage = ref(1)

const params = computed(() => ({
  page: currentPage.value,
  page_size: PAGE_SIZE,
  source_type: sourceTypeFilter.value === 'all' ? undefined : sourceTypeFilter.value,
}))

const { data: documentsData, pending: loading, refresh } = getDocuments(params)

const documents = computed(() => documentsData.value?.items || [])
const total = computed(() => documentsData.value?.total || 0)

// 切换筛选时回到第一页
watch(sourceTypeFilter, () => {
  currentPage.value = 1
  selectedIds.value = new Set()
})

// 翻页时清空选中
watch(currentPage, () => {
  selectedIds.value = new Set()
})

// 爬虫状态面板
const showCrawlerPanel = ref(true)

const { data: crawlerData, pending: loadingCrawler, refresh: refreshCrawler } = getCrawlerStatus()

const crawlerStatus = computed(() => crawlerData.value?.items || [])
const runningCrawler = ref<string | null>(null)

// 多选
const selectedIds = ref<Set<number>>(new Set())

function toggleSelect(id: number) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function toggleSelectAll(val: boolean | 'indeterminate') {
  selectedIds.value = val === true ? new Set(documents.value.map(d => d.id)) : new Set()
}

// 批量删除
async function handleBatchDelete() {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '确认批量删除',
    message: `确定要删除选中的 ${selectedIds.value.size} 篇文档吗？此操作不可撤销。`,
    confirmText: '删除',
    type: 'error',
  })
  if (!confirmed) return
  try {
    const res = await deleteDocuments([...selectedIds.value])
    toast.add({ title: `已删除 ${res.deleted} 篇${res.skipped ? `，跳过 ${res.skipped} 篇` : ''}`, color: 'success' })
    selectedIds.value = new Set()
    refresh()
  } catch {
    // 错误已由 apiRequest 统一处理
  }
}

// 查看文档
const viewingId = ref<number | null>(null)

async function handleView(doc: KnowledgeDocument) {
  viewingId.value = doc.id
  try {
    await viewDocument(doc.id)
  } catch {
    toast.add({ title: '无法打开文档', color: 'error' })
  } finally {
    viewingId.value = null
  }
}

// 删除
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
  currentPage.value = 1
  selectedIds.value = new Set()
  refresh()
}

// 删除
async function handleDelete(doc: KnowledgeDocument) {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '确认删除',
    message: `确定要删除文档「${doc.title}」吗？此操作不可撤销。`,
    confirmText: '删除',
    type: 'error',
  })
  if (!confirmed) return
  deletingId.value = doc.id
  try {
    await deleteDocument(doc.id)
    toast.add({ title: '删除成功', color: 'success' })
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
