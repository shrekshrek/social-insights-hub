import type { StrategyStatus } from '../types'

export const STATUS_MAP: Record<StrategyStatus, { label: string; color: 'neutral' | 'info' | 'warning' | 'success' }> = {
  draft: { label: '草稿', color: 'neutral' },
  planned: { label: '已规划', color: 'info' },
  probing: { label: '探测中', color: 'info' },
  collecting: { label: '采集中', color: 'info' },
  ready: { label: '数据就绪', color: 'warning' },
  phase1_done: { label: '洞察完成', color: 'warning' },
  phase2_done: { label: '策略完成', color: 'warning' },
  completed: { label: '已完成', color: 'success' },
}

export const STATUS_ORDER: Record<StrategyStatus, number> = {
  draft: 0, planned: 1, probing: 2, collecting: 3,
  ready: 4, phase1_done: 5, phase2_done: 6, completed: 7,
}

const PLATFORM_OPTIONS = [
  { code: 'douyin', label: '抖音' },
  { code: 'xiaohongshu', label: '小红书' },
  { code: 'weibo', label: '微博' },
  { code: 'bilibili', label: 'B站' },
  { code: 'kuaishou', label: '快手' },
  { code: 'zhihu', label: '知乎' },
  { code: 'tieba', label: '贴吧' },
] as const

export { PLATFORM_OPTIONS }

const PLATFORM_LABEL_MAP: Record<string, string> = {
  // long codes (used by LLM / research_design)
  douyin: '抖音', xiaohongshu: '小红书', weibo: '微博',
  bilibili: 'B站', kuaishou: '快手', zhihu: '知乎', tieba: '贴吧',
  // short codes (used by backend DataTask.platform.code)
  dy: '抖音', xhs: '小红书', wb: '微博',
  bili: 'B站', ks: '快手',
}

export const platformLabel = (code: string): string => PLATFORM_LABEL_MAP[code] || code

export const CHANNEL_LABELS: Record<string, string> = {
  social_media: '社交媒体',
  knowledge_base: '市场知识库',
  news_media: '新闻媒体',
}

export const formatDate = (dateString: string): string => {
  return new Date(dateString).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
