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
  campaign_strategy: '品牌传播策略 (Insight → Brand Role → Big Idea)',
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

// ==================== Sentiment（情感数值映射）====================
//
// 后端策略产出层的 sentiment 字段（Agenda Map narrative.sentiment、
// Landscape player.media_sentiment 等）统一为 [-2, 2] 加权数值；
// 0-source 实体可能为 null。**不混用 'positive'/'negative' 字符串。**
//
// 阈值：±0.5
//   -  >  0.5 → 正面（success 色）
//   -  < -0.5 → 负面（error 色）
//   - else    → 中性（neutral 色）
//
// 0.5 选择依据：[-2, 2] 全程 4 单位，±0.5 = 1/4 半程，对应"明显倾向"，
// 避免把 0.1 等微弱倾向误标为正/负面（旧版用 0-1 范围阈值导致 0.0
// 被误判为负面）。

export type SentimentValue = number | null | undefined

export const SENTIMENT_POSITIVE_THRESHOLD = 0.5
export const SENTIMENT_NEGATIVE_THRESHOLD = -0.5

export const sentimentColor = (s: SentimentValue): 'success' | 'error' | 'neutral' => {
  if (typeof s !== 'number') return 'neutral'
  if (s > SENTIMENT_POSITIVE_THRESHOLD) return 'success'
  if (s < SENTIMENT_NEGATIVE_THRESHOLD) return 'error'
  return 'neutral'
}

export const sentimentLabel = (s: SentimentValue): '正面' | '负面' | '中性' => {
  if (typeof s !== 'number') return '中性'
  if (s > SENTIMENT_POSITIVE_THRESHOLD) return '正面'
  if (s < SENTIMENT_NEGATIVE_THRESHOLD) return '负面'
  return '中性'
}
