<script setup lang="ts">
import type { SocialProject } from '../../../types'

definePageMeta({
  middleware: 'auth',
  layout: 'default',
})

const { getProjects, deleteProject } = useSocialProjects()

// 分页和搜索
const currentPage = ref(1)
const pageSize = ref(10)
const searchQuery = ref('')
const refreshing = ref(false)

// 获取项目列表
const params = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  search: searchQuery.value || undefined,
}))

const { data: projectsData, pending: loading, refresh } = getProjects(params)

const projects = computed(() => projectsData.value?.items || [])
const total = computed(() => projectsData.value?.total || 0)

// 刷新列表
const handleRefresh = async () => {
  refreshing.value = true
  await refresh()
  refreshing.value = false
}

// 删除项目
const handleDelete = async (project: SocialProject) => {
  const confirmed = await confirm(`确定要删除项目 "${project.name}" 吗？此操作不可恢复。`)
  if (!confirmed) return

  try {
    await deleteProject(project.id)
    await handleRefresh()
  } catch (error) {
    console.error('删除项目失败:', error)
  }
}

// 表格列定义
const columns = [
  {
    key: 'name',
    label: '项目名称',
  },
  {
    key: 'platforms',
    label: '平台',
  },
  {
    key: 'keywords',
    label: '关键词',
  },
  {
    key: 'owner_username',
    label: '创建者',
  },
  {
    key: 'created_at',
    label: '创建时间',
  },
  {
    key: 'actions',
    label: '操作',
  },
]

// 格式化日期
const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          社交媒体项目
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          管理您的社交媒体数据采集项目
        </p>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          icon="i-heroicons-plus"
          @click="navigateTo('/social-insights/projects/create')"
        >
          新建项目
        </UButton>
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

    <!-- 项目列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">
            项目列表
          </h2>
          <UInput
            v-model="searchQuery"
            placeholder="搜索项目名称或关键词..."
            icon="i-heroicons-magnifying-glass"
            class="w-80"
          />
        </div>
      </template>

      <!-- 项目表格 -->
      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">
              加载项目列表中...
            </p>
          </div>
        </template>

        <UTable
          :data="projects"
          :columns="columns"
          :loading="loading"
          class="w-full"
        >
          <template #platforms-data="{ row }">
            <div class="flex flex-wrap gap-1">
              <UBadge
                v-for="platform in row.platforms"
                :key="platform.id"
                variant="subtle"
                size="xs"
              >
                {{ platform.name }}
              </UBadge>
            </div>
          </template>

          <template #keywords-data="{ row }">
            <span class="text-sm text-gray-600 dark:text-gray-400">
              {{ row.keywords || '-' }}
            </span>
          </template>

          <template #created_at-data="{ row }">
            <span class="text-sm text-gray-600 dark:text-gray-400">
              {{ formatDate(row.created_at) }}
            </span>
          </template>

          <template #actions-data="{ row }">
            <div class="flex items-center gap-2">
              <UButton
                size="xs"
                variant="ghost"
                icon="i-heroicons-eye"
                @click="navigateTo(`/social-insights/projects/${row.id}`)"
              >
                查看
              </UButton>
              <UButton
                size="xs"
                variant="ghost"
                icon="i-heroicons-trash"
                color="red"
                @click="handleDelete(row)"
              >
                删除
              </UButton>
            </div>
          </template>
        </UTable>
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
            />
          </div>
        </ClientOnly>
      </template>
    </UCard>
  </div>
</template>
