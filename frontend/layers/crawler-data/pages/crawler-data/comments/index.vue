<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">评论数据</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">查看和管理爬取的评论内容</p>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          variant="outline"
          icon="i-heroicons-arrow-path"
          :loading="refreshing"
          @click="handleRefresh"
        >
          刷新
        </UButton>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <UCard>
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-600 dark:text-gray-400">总评论数</p>
            <p class="text-2xl font-bold mt-1">{{ stats.total }}</p>
          </div>
          <div class="p-3 bg-primary-100 dark:bg-primary-900/20 rounded-lg">
            <UIcon name="i-heroicons-chat-bubble-left" class="text-2xl text-primary-600 dark:text-primary-400" />
          </div>
        </div>
      </UCard>

      <UCard v-for="(count, platform) in stats.byPlatform" :key="platform">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-600 dark:text-gray-400">{{ PLATFORM_LABELS[platform] || platform }}</p>
            <p class="text-2xl font-bold mt-1">{{ count }}</p>
          </div>
        </div>
      </UCard>
    </div>

    <!-- 评论列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between gap-4">
          <h2 class="text-lg font-semibold">评论列表</h2>
          <div class="flex items-center gap-3">
            <USelect
              v-model="filters.platform"
              :items="platformOptions"
              placeholder="全部平台"
              clearable
              class="w-40"
            />
            <UInput
              v-model="searchQuery"
              placeholder="搜索评论、作者..."
              icon="i-heroicons-magnifying-glass"
              class="w-60"
            />
          </div>
        </div>
      </template>

      <!-- 评论表格 -->
      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">加载评论列表中...</p>
          </div>
        </template>

        <UTable
          :data="paginatedComments"
          :columns="columns"
          :loading="loading"
          class="w-full"
        />
      </ClientOnly>

      <!-- 分页 -->
      <template #footer>
        <ClientOnly>
          <template #fallback>
            <div class="flex justify-between items-center">
              <div class="h-4 bg-gray-200 rounded w-32 animate-pulse" />
              <div class="h-8 bg-gray-200 rounded w-64 animate-pulse" />
            </div>
          </template>

          <div class="flex justify-between items-center">
            <div class="text-sm text-gray-500 dark:text-gray-400">
              显示 {{ (currentPage - 1) * pageSize + 1 }} 到
              {{ Math.min(currentPage * pageSize, total) }} 共
              {{ total }} 条记录
            </div>
            <UPagination
              v-model:page="currentPage"
              :total="total"
              :items-per-page="pageSize"
              :sibling-count="2"
              show-first
              show-last
              show-edges
              :disabled="total === 0"
            />
          </div>
        </ClientOnly>
      </template>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import type { Comment } from '../../../types'
import { PLATFORM_LABELS } from '../../../types'

definePageMeta({
  layout: 'default'
})

// API
const crawlerDataApi = useCrawlerDataApi()

// 状态
const loading = ref(false)
const refreshing = ref(false)
const comments = ref<Comment[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

// 过滤器
const filters = ref({
  platform: null as string | null
})
const searchQuery = ref('')

// 统计数据
const stats = ref({
  total: 0,
  byPlatform: {} as Record<string, number>
})

// 平台选项
const platformOptions = computed(() => {
  return [
    { label: '小红书', value: 'xhs' },
    { label: '微博', value: 'weibo' },
    { label: '抖音', value: 'douyin' },
    { label: '快手', value: 'kuaishou' },
    { label: '哔哩哔哩', value: 'bilibili' },
    { label: '百度贴吧', value: 'tieba' },
    { label: '知乎', value: 'zhihu' }
  ]
})

// 表格列定义
const columns = [
  {
    key: 'platform',
    label: '平台',
    width: '80px'
  },
  {
    key: 'content',
    label: '评论内容',
    width: '400px'
  },
  {
    key: 'author_name',
    label: '评论者',
    width: '150px'
  },
  {
    key: 'note_id',
    label: '所属笔记',
    width: '120px'
  },
  {
    key: 'stats',
    label: '互动',
    width: '100px'
  },
  {
    key: 'published_at',
    label: '发布时间',
    width: '150px'
  },
  {
    key: 'actions',
    label: '操作',
    width: '100px'
  }
]

// 过滤后的评论列表
const filteredComments = computed(() => {
  let result = comments.value

  // 平台过滤
  if (filters.value.platform) {
    result = result.filter(comment => comment.platform === filters.value.platform)
  }

  // 搜索过滤
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(comment =>
      comment.content.toLowerCase().includes(query) ||
      comment.author_name.toLowerCase().includes(query)
    )
  }

  return result
})

// 分页后的评论列表
const paginatedComments = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  const items = filteredComments.value.slice(start, end)

  return items.map(comment => ({
    ...comment,
    platform: h('span', {
      class: 'inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-primary-100 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
    }, PLATFORM_LABELS[comment.platform] || comment.platform),
    content: h('div', { class: 'space-y-1' }, [
      h('p', {
        class: 'text-sm line-clamp-2',
        title: comment.content
      }, comment.content),
      comment.parent_comment_id && h('span', {
        class: 'text-xs text-gray-500 dark:text-gray-400'
      }, '↳ 回复评论'),
      comment.ip_location && h('span', {
        class: 'text-xs text-gray-500 dark:text-gray-400'
      }, `📍 ${comment.ip_location}`)
    ]),
    author_name: h('div', { class: 'flex items-center gap-2' }, [
      comment.author_avatar
        ? h('img', {
          src: comment.author_avatar,
          alt: comment.author_name,
          class: 'w-6 h-6 rounded-full'
        })
        : h('div', {
          class: 'w-6 h-6 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center'
        }, [
          h('span', { class: 'text-xs text-gray-600 dark:text-gray-400' }, comment.author_name[0])
        ]),
      h('span', { class: 'text-sm' }, comment.author_name)
    ]),
    note_id: h('span', {
      class: 'text-xs font-mono text-gray-500 dark:text-gray-400',
      title: comment.note_id
    }, comment.note_id.substring(0, 12) + '...'),
    stats: h('div', { class: 'text-xs space-y-1' }, [
      h('div', { class: 'flex items-center gap-2' }, [
        h('span', { class: 'flex items-center gap-1' }, [
          h(resolveComponent('UIcon'), { name: 'i-heroicons-heart', class: 'text-red-500' }),
          h('span', {}, comment.like_count?.toLocaleString() || '0')
        ]),
        comment.sub_comment_count ? h('span', { class: 'flex items-center gap-1' }, [
          h(resolveComponent('UIcon'), { name: 'i-heroicons-chat-bubble-left', class: 'text-blue-500' }),
          h('span', {}, comment.sub_comment_count.toLocaleString())
        ]) : null
      ])
    ]),
    published_at: comment.published_at
      ? new Date(comment.published_at).toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      })
      : '-',
    actions: h('div', { class: 'flex items-center gap-1' }, [
      h(resolveComponent('UButton'), {
        color: 'neutral',
        variant: 'ghost',
        size: 'sm',
        icon: 'i-heroicons-eye',
        onClick: () => navigateTo(`/crawler-data/comments/${comment.id}`)
      }),
      h(resolveComponent('UButton'), {
        color: 'error',
        variant: 'ghost',
        size: 'sm',
        icon: 'i-heroicons-trash',
        onClick: async () => {
          const { $confirm } = useNuxtApp()
          const confirmed = await $confirm(`确定要删除这条评论吗？此操作不可恢复。`)
          if (!confirmed) return

          const toast = useToast()
          try {
            await crawlerDataApi.deleteComment(comment.id)
            toast.add({
              title: '删除成功',
              description: '评论已被删除',
              color: 'success'
            })
            await loadComments()
          } catch (error) {
            toast.add({
              title: '删除失败',
              description: (error as Error).message || '删除评论时发生错误',
              color: 'error'
            })
          }
        }
      })
    ])
  }))
})

// 加载评论列表
const loadComments = async () => {
  loading.value = true
  try {
    const result = await crawlerDataApi.getComments({
      skip: 0,
      limit: 1000 // 先获取所有数据，前端分页
    })
    comments.value = result.items
    total.value = result.total

    // 计算统计数据
    stats.value.total = result.total
    stats.value.byPlatform = result.items.reduce((acc, comment) => {
      acc[comment.platform] = (acc[comment.platform] || 0) + 1
      return acc
    }, {} as Record<string, number>)
  } catch (error) {
    console.error('Failed to load comments:', error)
    const toast = useToast()
    toast.add({
      title: '加载失败',
      description: '无法加载评论列表，请稍后重试',
      color: 'error'
    })
  } finally {
    loading.value = false
  }
}

// 刷新列表
const handleRefresh = async () => {
  refreshing.value = true
  try {
    await loadComments()
  } finally {
    refreshing.value = false
  }
}

// 监听过滤器变化
watch([filters, searchQuery], () => {
  currentPage.value = 1
  total.value = filteredComments.value.length
}, { deep: true })

// 监听 filteredComments 变化更新 total
watch(filteredComments, (newValue) => {
  total.value = newValue.length
})

// 初始加载
onMounted(() => {
  loadComments()
})
</script>
