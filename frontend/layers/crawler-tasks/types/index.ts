/**
 * 爬虫任务类型定义
 */

export enum TaskStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  PAUSED = 'paused',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled'
}

export enum PlatformType {
  XHS = 'xhs',
  WEIBO = 'weibo',
  DOUYIN = 'douyin',
  KUAISHOU = 'kuaishou',
  BILIBILI = 'bilibili',
  TIEBA = 'tieba',
  ZHIHU = 'zhihu'
}

export enum CrawlerType {
  SEARCH = 'search',
  DETAIL = 'detail',
  CREATOR = 'creator',
  HOMEFEED = 'homefeed'
}

export interface TaskConfig {
  keywords?: string
  urls?: string[]
  max_count: number
  enable_comments: boolean
  enable_sub_comments: boolean
  max_comments_per_item?: number
  sort_type?: string
  account_ids?: number[]
  proxy_enabled: boolean
  enable_checkpoint: boolean
  [key: string]: unknown
}

export interface CrawlerTask {
  id: number
  name: string
  platform: PlatformType
  crawler_type: CrawlerType
  status: TaskStatus
  config: TaskConfig
  progress: number
  crawled_count: number
  error_message?: string | null
  started_at?: string | null
  completed_at?: string | null
  checkpoint_id?: string | null
  created_by?: number | null
  created_at: string
  updated_at: string
}

export interface TaskLog {
  id: number
  task_id: number
  level: string
  message: string
  detail?: Record<string, unknown> | null
  created_at: string
}

export interface CrawlerTaskDetail extends CrawlerTask {
  logs: TaskLog[]
}

export interface TaskStatistics {
  total: number
  pending: number
  running: number
  completed: number
  failed: number
  cancelled: number
}

export interface TaskCreateRequest {
  name: string
  platform: PlatformType
  crawler_type: CrawlerType
  config: TaskConfig
}

export interface TaskUpdateRequest {
  name?: string
  config?: TaskConfig
  status?: TaskStatus
}

// 平台显示名称映射
export const PLATFORM_LABELS: Record<PlatformType, string> = {
  [PlatformType.XHS]: '小红书',
  [PlatformType.WEIBO]: '微博',
  [PlatformType.DOUYIN]: '抖音',
  [PlatformType.KUAISHOU]: '快手',
  [PlatformType.BILIBILI]: '哔哩哔哩',
  [PlatformType.TIEBA]: '百度贴吧',
  [PlatformType.ZHIHU]: '知乎'
}

// 爬取模式显示名称映射
export const CRAWLER_TYPE_LABELS: Record<CrawlerType, string> = {
  [CrawlerType.SEARCH]: '关键词搜索',
  [CrawlerType.DETAIL]: '帖子详情',
  [CrawlerType.CREATOR]: '创作者主页',
  [CrawlerType.HOMEFEED]: '首页推荐'
}

// 任务状态显示名称映射
export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  [TaskStatus.PENDING]: '待执行',
  [TaskStatus.RUNNING]: '执行中',
  [TaskStatus.PAUSED]: '已暂停',
  [TaskStatus.COMPLETED]: '已完成',
  [TaskStatus.FAILED]: '失败',
  [TaskStatus.CANCELLED]: '已取消'
}

// 任务状态颜色映射
export const TASK_STATUS_COLORS: Record<TaskStatus, string> = {
  [TaskStatus.PENDING]: 'gray',
  [TaskStatus.RUNNING]: 'blue',
  [TaskStatus.PAUSED]: 'yellow',
  [TaskStatus.COMPLETED]: 'green',
  [TaskStatus.FAILED]: 'red',
  [TaskStatus.CANCELLED]: 'gray'
}
export type CrawlerTaskResponse = CrawlerTask
