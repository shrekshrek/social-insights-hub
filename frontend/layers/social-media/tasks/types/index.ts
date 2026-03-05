/**
 * 社交媒体数据洞察 - TypeScript 类型定义
 */

// ==================== Platform ====================

export interface Platform {
  id: number
  name: string
  code: string
  description: string | null
  base_url: string
  icon_url: string | null
  created_at: string
  updated_at: string
}

// ==================== Monitor ====================

export interface Monitor {
  id: number
  name: string
  description: string | null
  start_date: string | null
  end_date: string | null
  owner_id: number
  deep_analysis_settings: Record<string, unknown> | null
  created_at: string
  updated_at: string
  participant_ids?: number[]
  owner_username?: string
  participant_usernames?: string[]
}

export interface QuickTaskCreate {
  platform_ids: number[]
  task_type: 'search' | 'homefeed'
  data_source: DataSource
  keywords?: string
  // 远程爬虫高级选项
  max_notes_count?: number
  enable_comments?: boolean
  per_note_max_comments_count?: number
  // 平台特定选项
  publish_time_type?: number // 抖音专属
  sort_type?: string // 小红书专属
  // 自动分析
  auto_analyze?: boolean
}

export interface MonitorCreate {
  name: string
  description?: string
  start_date?: string
  end_date?: string
  participant_ids?: number[]
  quick_tasks?: QuickTaskCreate
}

export interface MonitorUpdate {
  name?: string
  description?: string
  start_date?: string
  end_date?: string
}

export interface MonitorCreateResponse {
  monitor: Monitor
  created_tasks: DataTaskWithRelations[]
}

export interface BatchTasksCreateResponse {
  created_tasks: DataTaskWithRelations[]
}

// ==================== Data Task ====================

export type TaskType = 'search' | 'detail' | 'creator' | 'homefeed'
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'
export type DataSource = 'remote_crawler' | 'local_upload'

export interface DataTask {
  id: number
  name: string
  description: string | null
  monitor_id: number
  platform_id: number
  creator_id: number
  task_type: TaskType
  keywords: string | null
  task_params: Record<string, unknown> | null
  data_source: DataSource
  status: TaskStatus
  posts_count: number
  comments_count: number
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export interface DataTaskWithRelations extends DataTask {
  monitor_name: string | null
  platform_name: string | null
  platform_code: string | null
  creator_username: string | null
}

export interface DataTaskCreate {
  name: string
  description?: string
  monitor_id: number
  platform_id: number
  task_type: TaskType
  keywords?: string
  task_params?: Record<string, unknown>
  data_source: DataSource
  auto_analyze?: boolean
}

export interface DataTaskUpdate {
  name?: string
  description?: string
  keywords?: string
  task_params?: Record<string, unknown>
}

// ==================== Social Post ====================

export interface SocialPost {
  id: number
  task_id: number
  platform_id: number
  post_id_on_platform: string
  post_type: string | null
  title: string | null
  content: string | null
  author_id: string | null
  author_name: string | null
  likes_count: number
  comments_count: number
  shares_count: number
  collected_count: number
  views_count: number
  danmaku_count: number
  images: string[] | null
  videos: string[] | null
  published_at: string | null
  url: string | null
  raw_data: Record<string, unknown> | null
  collected_at: string
  is_deleted: boolean
  created_at: string
  updated_at: string
  // 已爬取的评论数（与平台显示的 comments_count 区分）
  crawled_comments_count: number
}

export interface SocialPostCreate {
  post_id_on_platform: string
  post_type?: string
  title?: string
  content?: string
  author_id?: string
  author_name?: string
  likes_count?: number
  comments_count?: number
  shares_count?: number
  collected_count?: number
  views_count?: number
  danmaku_count?: number
  images?: string[]
  videos?: string[]
  published_at?: string
  url?: string
  raw_data?: Record<string, unknown>
}

export interface SocialPostWithComments extends SocialPost {
  comments: SocialComment[]
}

// ==================== Social Comment ====================

export interface SocialComment {
  id: number
  task_id: number
  post_id: number
  platform_id: number
  comment_id_on_platform: string
  parent_comment_id: string | null
  content: string | null
  author_id: string | null
  author_name: string | null
  likes_count: number
  sub_comments_count: number
  images: string[] | null
  published_at: string | null
  raw_data: Record<string, unknown> | null
  collected_at: string
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export interface SocialCommentCreate {
  comment_id_on_platform: string
  parent_comment_id?: string
  content?: string
  author_id?: string
  author_name?: string
  likes_count?: number
  sub_comments_count?: number
  images?: string[]
  published_at?: string
  raw_data?: Record<string, unknown>
}

// ==================== JSON Upload ====================

export interface JSONUploadData {
  contents: SocialPostCreate[]
  comments: SocialCommentCreate[]
}

export interface JSONUploadResponse {
  task_id: number
  posts_imported: number
  comments_imported: number
  message: string
}

// ==================== API Responses ====================

export interface PostQueryResponse {
  posts: SocialPost[]
  total_tasks: number
  message: string
}

export interface PostListResponse {
  items: SocialPost[]
  total: number
  page: number
  page_size: number
}

export interface CommentListResponse {
  items: SocialComment[]
  total: number
  page: number
  page_size: number
}
