/**
 * 帖子分析表格列定义 composable
 *
 * 提供统一的表格列定义，可在 AnalysisPanel 和 PostListModal 中共用
 */
import { computed, h, type Component } from 'vue'
import { UBadge, UIcon } from '#components'
import type { TableColumn } from '@nuxt/ui'
import type { PostAnalysisWithPostInfo } from '../types'
import ExpandableText from '../components/shared/ExpandableText.vue'

export interface PostAnalysisColumnsOptions {
  /** 点击深度分析按钮的回调 */
  onOpenDeepResult?: (postId: number, type: 'post' | 'comment') => void
  /** 标题/内容列的宽度 */
  contentColumnSize?: number
}

/**
 * 格式化数字显示
 */
const formatNumber = (num?: number | null) => {
  if (num == null) return '-'
  if (num >= 10000) return `${(num / 10000).toFixed(1)}万`
  return num.toLocaleString()
}

/**
 * 格式化日期时间
 */
const formatDateTime = (value?: string | null): { date: string; time: string } | null => {
  if (!value) return null
  const d = new Date(value)
  if (isNaN(d.getTime())) return null
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return {
    date: `${year}-${month}-${day}`,
    time: `${hour}:${min}`,
  }
}

/**
 * 获取帖子分析表格列定义
 */
export function usePostAnalysisColumns(options: PostAnalysisColumnsOptions = {}) {
  const {
    onOpenDeepResult,
    contentColumnSize = 160,
  } = options

  const columns = computed<TableColumn<PostAnalysisWithPostInfo>[]>(() => {
    const Badge = UBadge as Component
    const Icon = UIcon as Component

    return [
      // ID 列
      {
        accessorKey: 'post_id',
        header: 'ID',
        size: 40,
        cell: ({ row }) => h('span', { class: 'text-xs text-gray-500 font-mono' }, row.original.post_id),
      },
      // 平台ID 列
      {
        accessorKey: 'post_id_on_platform',
        header: '平台ID',
        size: 80,
        cell: ({ row }) => {
          const platformId = row.original.post_id_on_platform
          const url = row.original.url
          return h('div', { class: 'space-y-1' }, [
            h('span', {
              class: 'text-xs text-gray-500 font-mono truncate block max-w-[70px]',
              title: platformId || '-'
            }, platformId || '-'),
            url
              ? h('a', {
                  href: url,
                  target: '_blank',
                  rel: 'noopener noreferrer',
                  class: 'flex items-center gap-0.5 text-xs text-primary-500 hover:text-primary-600',
                  onClick: (e: Event) => e.stopPropagation()
                }, [
                  h(Icon, { name: 'i-heroicons-arrow-top-right-on-square', class: 'w-3 h-3' }),
                  h('span', '原文')
                ])
              : null
          ])
        },
      },
      // 标题/内容 列
      {
        accessorKey: 'content',
        header: '标题/内容',
        size: contentColumnSize,
        cell: ({ row }) =>
          h(ExpandableText, {
            title: row.original.title || '',
            content: row.original.content || '',
            maxLength: 30,
          }),
      },
      // 初筛 列
      {
        accessorKey: 'scores',
        header: '初筛',
        size: 65,
        cell: ({ row }) => {
          const { spam_score, value_score, relevance_score } = row.original
          const scoreText = (label: string, value?: number | null) =>
            h('div', { class: 'flex items-center gap-1 text-xs' }, [
              h('span', { class: 'text-gray-500' }, label),
              h(
                'span',
                { class: value == null ? 'text-gray-400' : 'font-medium' },
                value == null ? '-' : value.toFixed(1),
              ),
            ])

          return h('div', { class: 'space-y-0.5' }, [
            scoreText('广告', spam_score),
            scoreText('价值', value_score),
            scoreText('相关', relevance_score),
          ])
        },
      },
      // 情感 列
      {
        accessorKey: 'sentiment',
        header: '情感',
        size: 60,
        cell: ({ row }) => {
          const sentiment = row.original.sentiment
          if (sentiment == null) {
            return h('span', { class: 'text-gray-400 text-xs' }, '-')
          }
          const sentimentMap: Record<number, { color: string; label: string }> = {
            [-2]: { color: 'error', label: '强烈负面' },
            [-1]: { color: 'warning', label: '轻度负面' },
            [0]: { color: 'neutral', label: '中性' },
            [1]: { color: 'info', label: '轻度正面' },
            [2]: { color: 'success', label: '强烈正面' },
          }
          const config = sentimentMap[sentiment] || { color: 'neutral', label: '中性' }
          return h(Badge, { size: 'xs', color: config.color, variant: 'subtle' }, () => config.label)
        },
      },
      // CII 列
      {
        accessorKey: 'cii',
        header: 'CII',
        size: 50,
        cell: ({ row }) => {
          const cii = row.original.cii
          if (cii == null) {
            return h('span', { class: 'text-gray-400 text-xs' }, '-')
          }
          const getColor = (value: number) => {
            if (value >= 70) return 'text-green-600'
            if (value >= 40) return 'text-yellow-600'
            return 'text-gray-600'
          }
          return h('span', { class: `text-sm font-medium ${getColor(cii)}` }, cii.toFixed(1))
        },
      },
      // 深度 列
      {
        accessorKey: 'deep_analysis',
        header: '深度',
        size: 50,
        cell: ({ row }) => {
          const { post_deep_result, comment_deep_result, post_id } = row.original
          const hasPostDeep = !!post_deep_result
          const hasCommentDeep = !!comment_deep_result

          if (!hasPostDeep && !hasCommentDeep) {
            return h('span', { class: 'text-gray-400 text-xs' }, '-')
          }

          return h('div', { class: 'space-y-1' }, [
            hasPostDeep
              ? h(
                  'button',
                  {
                    class: 'flex items-center gap-1 text-xs text-green-600 hover:text-green-700 cursor-pointer',
                    onClick: () => onOpenDeepResult?.(post_id, 'post'),
                  },
                  [
                    h(Icon, { name: 'i-heroicons-document-text', class: 'w-3 h-3' }),
                    h('span', '原文'),
                  ]
                )
              : null,
            hasCommentDeep
              ? h(
                  'button',
                  {
                    class: 'flex items-center gap-1 text-xs text-orange-600 hover:text-orange-700 cursor-pointer',
                    onClick: () => onOpenDeepResult?.(post_id, 'comment'),
                  },
                  [
                    h(Icon, { name: 'i-heroicons-chat-bubble-left-right', class: 'w-3 h-3' }),
                    h('span', '评论'),
                  ]
                )
              : null,
          ])
        },
      },
      // 互动 列
      {
        accessorKey: 'engagement',
        header: '互动',
        size: 70,
        cell: ({ row }) => {
          const { likes_count, comments_count, shares_count, collected_count, views_count, danmaku_count } = row.original
          const items = [
            h('div', {}, `赞 ${formatNumber(likes_count)}`),
            h('div', {}, `评 ${formatNumber(comments_count)}`),
          ]
          if (shares_count > 0) {
            items.push(h('div', {}, `转 ${formatNumber(shares_count)}`))
          }
          if (collected_count > 0) {
            items.push(h('div', {}, `藏 ${formatNumber(collected_count)}`))
          }
          if (views_count > 0) {
            items.push(h('div', {}, `览 ${formatNumber(views_count)}`))
          }
          if (danmaku_count > 0) {
            items.push(h('div', {}, `弹 ${formatNumber(danmaku_count)}`))
          }
          return h('div', { class: 'text-xs space-y-0.5 text-gray-600 dark:text-gray-400' }, items)
        },
      },
      // 发布时间 列
      {
        accessorKey: 'published_at',
        header: '发布时间',
        size: 90,
        cell: ({ row }) => {
          const dt = formatDateTime(row.original.published_at)
          if (!dt) return h('span', { class: 'text-xs text-gray-400' }, '-')
          return h('div', { class: 'text-xs text-gray-500 leading-tight' }, [
            h('div', {}, dt.date),
            h('div', {}, dt.time),
          ])
        },
      },
    ]
  })

  return {
    columns,
    formatNumber,
    formatDateTime,
  }
}
