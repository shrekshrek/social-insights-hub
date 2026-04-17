<template>
  <div class="max-w-4xl mx-auto space-y-6">
    <!-- 搜索输入区域 -->
    <UCard>
      <template #header>
        <div class="flex items-center gap-4">
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
            RAG 检索测试
          </h1>
          <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">
            测试向量检索功能，输入查询词获取最相关的文档分块
          </p>
        </div>
      </template>

      <template #body>
        <div class="space-y-4">
          <UFormField label="查询词">
            <UInput
              v-model="query"
              placeholder="例如：小米SU7 品牌口碑、社交媒体平台趋势..."
              @keyup.enter="handleSearch"
            />
          </UFormField>

          <UFormField label="返回结果数">
            <div class="flex items-center gap-4">
              <UInput v-model.number="topK" type="number" min="1" max="20" />
              <UButton class="shrink-0" :loading="loading" @click="handleSearch">
                检索
              </UButton>
            </div>
          </UFormField>

          <UFormField :label="`上次查询：${lastQuery || '-'}`" />
        </div>
      </template>
    </UCard>

    <!-- 搜索结果 -->
    <UCard v-if="results.length > 0">
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">
            检索结果（共 {{ total }} 条）
          </h2>
        </div>
      </template>

      <template #body>
        <ClientOnly>
          <template #fallback>
            <div class="text-center py-4 text-gray-500">加载结果中...</div>
          </template>

          <div v-if="loading" class="text-center py-4 text-gray-500">
            加载中...
          </div>

          <div v-else class="divide-y divide-gray-100 dark:divide-gray-800">
            <div
              v-for="(result, idx) in results"
              :key="result.chunk_index"
              class="p-4 border-b border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              <div class="space-y-2">
                <!-- 相关度 -->
                <div class="flex items-center gap-2">
                  <UIcon name="i-heroicons-sparkles" class="w-4 h-4 text-yellow-500" />
                  <div class="min-w-0">
                    <p class="text-sm text-gray-600 dark:text-gray-400">
                      文档：<span class="font-medium text-gray-900 dark:text-white">{{ result.document_title }}</span>
                    </p>
                    <p class="text-sm text-gray-500">
                      相关度：{{ (result.score * 100).toFixed(1) }}%
                    </p>
                  </div>
                </div>

                <!-- 分块序号 -->
                <UBadge variant="subtle" class="shrink-0">分块 #{{ idx + 1 }}</UBadge>
              </div>

              <!-- 分块内容 -->
              <div class="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap break-words">
                <p class="text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap break-words">
                  {{ result.content }}
                </p>
              </div>
            </div>
          </div>
        </ClientOnly>
      </template>

      <template #footer>
        <div class="text-center py-2">
          <p class="text-sm text-gray-500">
            显示前 {{ results.length }} 条结果（按相关度排序）
          </p>
        </div>
      </template>
    </UCard>

    <!-- 无结果提示 -->
    <UCard v-else-if="query && !loading && results.length === 0">
      <div class="text-center py-12">
        <UIcon name="i-heroicons-magnifying-glass" class="w-12 h-12 text-gray-300 mx-auto mb-3" />
        <p class="text-gray-500">未找到相关文档分块</p>
        <p class="text-sm text-gray-400 mt-2">尝试调整查询词或上传更多相关文档</p>
      </div>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { ChunkResult } from '../../types'
import { UCard, UButton, UFormField, UBadge, UIcon } from '#components'

definePageMeta({ layout: 'default' })
useHead({ title: 'RAG 检索测试' })

const { searchDocuments } = useKnowledgeBaseApi()
const toast = useToast()

const query = ref('')
const topK = ref(6)
const loading = ref(false)
const results = ref<ChunkResult[]>([])
const total = ref(0)
const lastQuery = ref('')

async function handleSearch() {
  if (!query.value.trim()) {
    toast.add({ title: '请输入查询词', color: 'warning' })
    return
  }

  loading.value = true
  try {
    const res = await searchDocuments(query.value, topK.value)
    results.value = res.results
    total.value = res.total
    lastQuery.value = query.value
  } catch {
    // 错误已由 apiRequest 统一处理
  } finally {
    loading.value = false
  }
}
</script>
