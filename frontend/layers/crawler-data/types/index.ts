/**
 * 爬虫数据类型定义
 */

// 笔记数据
export interface Note {
  id: number
  platform: string
  note_id: string
  title: string
  content: string
  author_id: string
  author_name: string
  author_avatar?: string | null
  note_url?: string | null
  images?: string[] | null
  video_url?: string | null
  like_count?: number | null
  comment_count?: number | null
  share_count?: number | null
  collect_count?: number | null
  view_count?: number | null
  published_at?: string | null
  crawled_at: string
  created_at: string
  updated_at: string
}

// 评论数据
export interface Comment {
  id: number
  platform: string
  comment_id: string
  content: string
  note_id: string
  parent_comment_id?: string | null
  author_id: string
  author_name: string
  author_avatar?: string | null
  like_count?: number | null
  sub_comment_count?: number | null
  published_at?: string | null
  crawled_at: string
  ip_location?: string | null
  created_at: string
  updated_at: string
}

// 任务关联的笔记
export interface TaskNote {
  id: number
  task_id: number
  note_id: number
  note?: Note
  created_at: string
}

// 任务关联的评论
export interface TaskComment {
  id: number
  task_id: number
  comment_id: number
  comment?: Comment
  created_at: string
}

// 平台显示名称映射
export const PLATFORM_LABELS: Record<string, string> = {
  xhs: '小红书',
  weibo: '微博',
  douyin: '抖音',
  kuaishou: '快手',
  bilibili: '哔哩哔哩',
  tieba: '百度贴吧',
  zhihu: '知乎'
}

// 笔记列表查询参数
export interface NotesQueryParams {
  skip?: number
  limit?: number
  platform?: string
  author_id?: string
  keyword?: string
  start_date?: string
  end_date?: string
}

// 评论列表查询参数
export interface CommentsQueryParams {
  skip?: number
  limit?: number
  platform?: string
  note_id?: string
  author_id?: string
  keyword?: string
  start_date?: string
  end_date?: string
}
