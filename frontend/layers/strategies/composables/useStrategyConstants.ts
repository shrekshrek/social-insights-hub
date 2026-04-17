import type { OutputType, StrategyStatus } from '../types'

export const STATUS_MAP: Record<StrategyStatus, { label: string; color: 'neutral' | 'info' | 'warning' | 'success' }> = {
  draft: { label: '草稿', color: 'neutral' },
  planned: { label: '已规划', color: 'info' },
  probing: { label: '探测中', color: 'info' },
  collecting: { label: '采集中', color: 'info' },
  ready: { label: '数据就绪', color: 'warning' },
  // campaign_strategy 路径
  insight_done: { label: '洞察完成 (Insight)', color: 'warning' },
  brand_role_done: { label: '品牌角色完成 (Brand Role)', color: 'warning' },
  // market_report 路径
  agenda_map_done: { label: '媒体议程图完成 (Agenda Map)', color: 'warning' },
  landscape_done: { label: '竞争格局完成 (Landscape)', color: 'warning' },
  completed: { label: '已完成', color: 'success' },
}

/**
 * 状态顺序（两条产出路径共享同一 STATUS_ORDER 数值，便于"≥ready"等通用比较）。
 * campaign_strategy: insight_done=5 → brand_role_done=6 → completed=7
 * market_report:  agenda_map_done=5 → landscape_done=6 → completed=7
 */
export const STATUS_ORDER: Record<StrategyStatus, number> = {
  draft: 0, planned: 1, probing: 2, collecting: 3,
  ready: 4,
  insight_done: 5, brand_role_done: 6,
  agenda_map_done: 5, landscape_done: 6,
  completed: 7,
}

export const OUTPUT_TYPE_LABELS: Record<OutputType, string> = {
  campaign_strategy: '品牌策略 (Insight → Brand Role → Big Idea)',
  market_report: '市场分析报告 (Agenda Map → Landscape → Strategic Brief)',
  full_strategy: '全渠道综合策略 (Agenda Map → Landscape → Insight → Brand Role → Big Idea)',
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
  news_media: '新闻媒体',
  industry_research: '行业研究',
  creative_research: '创意研究',
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
