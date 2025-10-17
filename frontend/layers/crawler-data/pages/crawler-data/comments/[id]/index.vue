<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div v-if="loading" class="flex items-center justify-center min-h-[400px]">
    <UIcon name="i-heroicons-arrow-path" class="animate-spin text-4xl text-primary-600" />
  </div>

  <div v-else-if="comment" class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          @click="navigateTo('/crawler-data/comments')"
        >
          返回
        </UButton>
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">评论详情</h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">查看评论的详细信息</p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          color="error"
          variant="outline"
          icon="i-heroicons-trash"
          @click="handleDelete"
        >
          删除
        </UButton>
      </div>
    </div>

    <!-- 基本信息卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-information-circle" class="text-xl" />
          <h2 class="text-lg font-semibold">基本信息</h2>
        </div>
      </template>

      <div class="space-y-6">
        <!-- 平台和ID -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">平台</label>
            <p class="mt-1">
              <span class="inline-flex items-center px-2.5 py-0.5 rounded-md text-sm font-medium bg-primary-100 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300">
                {{ PLATFORM_LABELS[comment.platform] || comment.platform }}
              </span>
            </p>
          </div>
          <div>
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">评论ID</label>
            <p class="mt-1 text-sm font-mono text-gray-600 dark:text-gray-400">{{ comment.comment_id }}</p>
          </div>
        </div>

        <!-- 评论内容 -->
        <div>
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">评论内容</label>
          <p class="mt-2 text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{{ comment.content }}</p>
        </div>

        <!-- 作者信息 -->
        <div>
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">评论者</label>
          <div class="mt-2 flex items-center gap-3">
            <img
              v-if="comment.author_avatar"
              :src="comment.author_avatar"
              :alt="comment.author_name"
              class="w-12 h-12 rounded-full"
            >
            <div v-else class="w-12 h-12 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
              <span class="text-lg font-medium text-gray-600 dark:text-gray-400">
                {{ comment.author_name[0] }}
              </span>
            </div>
            <div>
              <p class="font-medium">{{ comment.author_name }}</p>
              <p class="text-sm text-gray-500 dark:text-gray-400">ID: {{ comment.author_id }}</p>
            </div>
          </div>
        </div>

        <!-- IP 位置 -->
        <div v-if="comment.ip_location">
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">IP 属地</label>
          <p class="mt-1 flex items-center gap-1">
            <UIcon name="i-heroicons-map-pin" class="text-gray-500" />
            <span>{{ comment.ip_location }}</span>
          </p>
        </div>

        <!-- 关联信息 -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">所属笔记ID</label>
            <p class="mt-1 text-sm font-mono text-gray-600 dark:text-gray-400">{{ comment.note_id }}</p>
          </div>
          <div v-if="comment.parent_comment_id">
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">回复评论ID</label>
            <p class="mt-1 text-sm font-mono text-gray-600 dark:text-gray-400">{{ comment.parent_comment_id }}</p>
          </div>
        </div>

        <!-- 评论类型标签 -->
        <div>
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">评论类型</label>
          <div class="mt-1">
            <span
              v-if="comment.parent_comment_id"
              class="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-blue-100 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300"
            >
              <UIcon name="i-heroicons-arrow-uturn-right" class="mr-1" />
              子评论（回复）
            </span>
            <span
              v-else
              class="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-300"
            >
              <UIcon name="i-heroicons-chat-bubble-left" class="mr-1" />
              顶级评论
            </span>
          </div>
        </div>
      </div>
    </UCard>

    <!-- 互动数据卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-chart-bar" class="text-xl" />
          <h2 class="text-lg font-semibold">互动数据</h2>
        </div>
      </template>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <div class="flex items-center gap-2 text-gray-600 dark:text-gray-400 mb-1">
            <UIcon name="i-heroicons-heart" class="text-red-500" />
            <span class="text-sm">点赞数</span>
          </div>
          <p class="text-2xl font-bold">{{ comment.like_count?.toLocaleString() || 0 }}</p>
        </div>
        <div>
          <div class="flex items-center gap-2 text-gray-600 dark:text-gray-400 mb-1">
            <UIcon name="i-heroicons-chat-bubble-left" class="text-blue-500" />
            <span class="text-sm">子评论数</span>
          </div>
          <p class="text-2xl font-bold">{{ comment.sub_comment_count?.toLocaleString() || 0 }}</p>
        </div>
      </div>
    </UCard>

    <!-- 时间信息卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-clock" class="text-xl" />
          <h2 class="text-lg font-semibold">时间信息</h2>
        </div>
      </template>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div>
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">发布时间</label>
          <p class="mt-1">
            {{ comment.published_at
              ? new Date(comment.published_at).toLocaleString('zh-CN', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
              })
              : '-'
            }}
          </p>
        </div>
        <div>
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">爬取时间</label>
          <p class="mt-1">
            {{ new Date(comment.crawled_at).toLocaleString('zh-CN', {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit'
            }) }}
          </p>
        </div>
        <div>
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">记录创建时间</label>
          <p class="mt-1">
            {{ new Date(comment.created_at).toLocaleString('zh-CN', {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit'
            }) }}
          </p>
        </div>
      </div>
    </UCard>
  </div>

  <div v-else class="flex items-center justify-center min-h-[400px]">
    <div class="text-center">
      <UIcon name="i-heroicons-exclamation-triangle" class="text-4xl text-gray-400 mb-2" />
      <p class="text-gray-600 dark:text-gray-400">未找到评论</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Comment } from '../../../../types'
import { PLATFORM_LABELS } from '../../../../types'

definePageMeta({
  layout: 'default'
})

const route = useRoute()
const commentId = computed(() => parseInt(route.params.id as string))

// API
const crawlerDataApi = useCrawlerDataApi()

// 状态
const loading = ref(true)
const comment = ref<Comment | null>(null)

// 加载评论详情
const loadComment = async () => {
  loading.value = true
  try {
    comment.value = await crawlerDataApi.getComment(commentId.value)
  } catch (error) {
    console.error('Failed to load comment:', error)
    const toast = useToast()
    toast.add({
      title: '加载失败',
      description: '无法加载评论详情，请稍后重试',
      color: 'error'
    })
  } finally {
    loading.value = false
  }
}

// 删除评论
const handleDelete = async () => {
  if (!comment.value) return

  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm('确定要删除这条评论吗？此操作不可恢复。')
  if (!confirmed) return

  const toast = useToast()
  try {
    await crawlerDataApi.deleteComment(comment.value.id)
    toast.add({
      title: '删除成功',
      description: '评论已被删除',
      color: 'success'
    })
    navigateTo('/crawler-data/comments')
  } catch (error) {
    toast.add({
      title: '删除失败',
      description: (error as Error).message || '删除评论时发生错误',
      color: 'error'
    })
  }
}

// 初始加载
onMounted(() => {
  loadComment()
})
</script>
