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

// ==================== Social Project ====================

export interface SocialProject {
  id: number
  name: string
  description: string | null
  keywords: string | null
  project_start_date: string | null
  project_end_date: string | null
  owner_id: number
  deep_analysis_settings: Record<string, any> | null
  created_at: string
  updated_at: string
  platforms?: Platform[]
  participant_ids?: number[]
  owner_username?: string
}

export interface SocialProjectCreate {
  name: string
  description?: string
  keywords?: string
  project_start_date?: string
  project_end_date?: string
  platform_ids: number[]
  participant_ids?: number[]
  deep_analysis_settings?: Record<string, any>
}

export interface SocialProjectUpdate {
  name?: string
  description?: string
  keywords?: string
  project_start_date?: string
  project_end_date?: string
  platform_ids?: number[]
  participant_ids?: number[]
  deep_analysis_settings?: Record<string, any>
}

// ==================== Data Task ====================

export type TaskType = 'search' | 'detail' | 'creator' | 'homefeed'
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'
export type DataSource = 'remote_crawler' | 'local_upload'

export interface DataTask {
  id: number
  name: string
  description: string | null
  project_id: number
  platform_id: number
  creator_id: number
  task_type: TaskType
  keywords: string | null
  task_params: Record<string, any> | null
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
  project_name: string | null
  platform_name: string | null
  platform_code: string | null
  creator_username: string | null
}

export interface DataTaskCreate {
  name: string
  description?: string
  project_id: number
  platform_id: number
  task_type: TaskType
  keywords?: string
  task_params?: Record<string, any>
  data_source: DataSource
}

export interface DataTaskUpdate {
  name?: string
  description?: string
  keywords?: string
  task_params?: Record<string, any>
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
  views_count: number
  images: string[] | null
  videos: string[] | null
  published_at: string | null
  url: string | null
  raw_data: Record<string, any> | null
  collected_at: string
  is_deleted: boolean
  created_at: string
  updated_at: string
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
  views_count?: number
  images?: string[]
  videos?: string[]
  published_at?: string
  url?: string
  raw_data?: Record<string, any>
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
  raw_data: Record<string, any> | null
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
  raw_data?: Record<string, any>
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

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface PostQueryResponse {
  posts: SocialPost[]
  total_tasks: number
  message: string
}
