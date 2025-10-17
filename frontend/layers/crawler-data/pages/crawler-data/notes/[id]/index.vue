<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div v-if="loading" class="flex items-center justify-center min-h-[400px]">
    <UIcon name="i-heroicons-arrow-path" class="animate-spin text-4xl text-primary-600" />
  </div>

  <div v-else-if="note" class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          @click="navigateTo('/crawler-data/notes')"
        >
          返回
        </UButton>
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">笔记详情</h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">查看笔记的详细信息</p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          v-if="note.note_url"
          variant="outline"
          icon="i-heroicons-arrow-top-right-on-square"
          :to="note.note_url"
          target="_blank"
        >
          查看原文
        </UButton>
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
        <!-- 标题 -->
        <div>
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">标题</label>
          <p class="mt-1 text-base">{{ note.title }}</p>
        </div>

        <!-- 平台和ID -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">平台</label>
            <p class="mt-1">
              <span class="inline-flex items-center px-2.5 py-0.5 rounded-md text-sm font-medium bg-primary-100 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300">
                {{ PLATFORM_LABELS[note.platform] || note.platform }}
              </span>
            </p>
          </div>
          <div>
            <label class="text-sm font-medium text-gray-700 dark:text-gray-300">笔记ID</label>
            <p class="mt-1 text-sm font-mono text-gray-600 dark:text-gray-400">{{ note.note_id }}</p>
          </div>
        </div>

        <!-- 作者信息 -->
        <div>
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">作者</label>
          <div class="mt-2 flex items-center gap-3">
            <img
              v-if="note.author_avatar"
              :src="note.author_avatar"
              :alt="note.author_name"
              class="w-12 h-12 rounded-full"
            >
            <div v-else class="w-12 h-12 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
              <span class="text-lg font-medium text-gray-600 dark:text-gray-400">
                {{ note.author_name[0] }}
              </span>
            </div>
            <div>
              <p class="font-medium">{{ note.author_name }}</p>
              <p class="text-sm text-gray-500 dark:text-gray-400">ID: {{ note.author_id }}</p>
            </div>
          </div>
        </div>

        <!-- 内容 -->
        <div>
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">内容</label>
          <p class="mt-2 text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{{ note.content }}</p>
        </div>

        <!-- 图片 -->
        <div v-if="note.images && note.images.length > 0">
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">图片 ({{ note.images.length }})</label>
          <div class="mt-2 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            <a
              v-for="(image, index) in note.images"
              :key="index"
              :href="image"
              target="_blank"
              class="group relative aspect-square rounded-lg overflow-hidden bg-gray-100 dark:bg-gray-800"
            >
              <img
                :src="image"
                :alt="`图片 ${index + 1}`"
                class="w-full h-full object-cover group-hover:scale-105 transition-transform"
              >
              <div class="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
            </a>
          </div>
        </div>

        <!-- 视频 -->
        <div v-if="note.video_url">
          <label class="text-sm font-medium text-gray-700 dark:text-gray-300">视频</label>
          <a
            :href="note.video_url"
            target="_blank"
            class="mt-2 inline-flex items-center gap-2 text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
          >
            <UIcon name="i-heroicons-play-circle" class="text-xl" />
            <span>查看视频</span>
          </a>
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

      <div class="grid grid-cols-2 md:grid-cols-5 gap-6">
        <div>
          <div class="flex items-center gap-2 text-gray-600 dark:text-gray-400 mb-1">
            <UIcon name="i-heroicons-heart" class="text-red-500" />
            <span class="text-sm">点赞</span>
          </div>
          <p class="text-2xl font-bold">{{ note.like_count?.toLocaleString() || 0 }}</p>
        </div>
        <div>
          <div class="flex items-center gap-2 text-gray-600 dark:text-gray-400 mb-1">
            <UIcon name="i-heroicons-chat-bubble-left" class="text-blue-500" />
            <span class="text-sm">评论</span>
          </div>
          <p class="text-2xl font-bold">{{ note.comment_count?.toLocaleString() || 0 }}</p>
        </div>
        <div>
          <div class="flex items-center gap-2 text-gray-600 dark:text-gray-400 mb-1">
            <UIcon name="i-heroicons-bookmark" class="text-yellow-500" />
            <span class="text-sm">收藏</span>
          </div>
          <p class="text-2xl font-bold">{{ note.collect_count?.toLocaleString() || 0 }}</p>
        </div>
        <div>
          <div class="flex items-center gap-2 text-gray-600 dark:text-gray-400 mb-1">
            <UIcon name="i-heroicons-share" class="text-green-500" />
            <span class="text-sm">分享</span>
          </div>
          <p class="text-2xl font-bold">{{ note.share_count?.toLocaleString() || 0 }}</p>
        </div>
        <div>
          <div class="flex items-center gap-2 text-gray-600 dark:text-gray-400 mb-1">
            <UIcon name="i-heroicons-eye" class="text-purple-500" />
            <span class="text-sm">浏览</span>
          </div>
          <p class="text-2xl font-bold">{{ note.view_count?.toLocaleString() || 0 }}</p>
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
            {{ note.published_at
              ? new Date(note.published_at).toLocaleString('zh-CN', {
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
            {{ new Date(note.crawled_at).toLocaleString('zh-CN', {
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
            {{ new Date(note.created_at).toLocaleString('zh-CN', {
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
      <p class="text-gray-600 dark:text-gray-400">未找到笔记</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Note } from '../../../../types'
import { PLATFORM_LABELS } from '../../../../types'

definePageMeta({
  layout: 'default'
})

const route = useRoute()
const noteId = computed(() => parseInt(route.params.id as string))

// API
const crawlerDataApi = useCrawlerDataApi()

// 状态
const loading = ref(true)
const note = ref<Note | null>(null)

// 加载笔记详情
const loadNote = async () => {
  loading.value = true
  try {
    note.value = await crawlerDataApi.getNote(noteId.value)
  } catch (error) {
    console.error('Failed to load note:', error)
    const toast = useToast()
    toast.add({
      title: '加载失败',
      description: '无法加载笔记详情，请稍后重试',
      color: 'error'
    })
  } finally {
    loading.value = false
  }
}

// 删除笔记
const handleDelete = async () => {
  if (!note.value) return

  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm(`确定要删除笔记 "${note.value.title}" 吗？此操作不可恢复。`)
  if (!confirmed) return

  const toast = useToast()
  try {
    await crawlerDataApi.deleteNote(note.value.id)
    toast.add({
      title: '删除成功',
      description: `笔记 "${note.value.title}" 已被删除`,
      color: 'success'
    })
    navigateTo('/crawler-data/notes')
  } catch (error) {
    toast.add({
      title: '删除失败',
      description: (error as Error).message || '删除笔记时发生错误',
      color: 'error'
    })
  }
}

// 初始加载
onMounted(() => {
  loadNote()
})
</script>
