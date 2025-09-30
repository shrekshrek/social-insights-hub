// 通用类型定义，供所有模块共享使用

// 确认对话框选项类型
export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  type?: 'warning' | 'error' | 'info' | 'success';
}

// 分页相关类型
export interface PaginationParams {
  page?: number;
  page_size?: number;
  search?: string; // 可选的搜索参数
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages?: number; // 可选的总页数
  has_next?: boolean;   // 是否有下一页
  has_prev?: boolean;   // 是否有上一页
}

// 表单验证类型
export interface FormErrors {
  [key: string]: string[];
}

// 通用状态类型
export type LoadingState = 'idle' | 'loading' | 'success' | 'error'

// 通用操作结果类型
export interface OperationResult<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

// @nuxt/ui 兼容的颜色类型
export type UIColor = 'primary' | 'secondary' | 'success' | 'info' | 'warning' | 'error' | 'neutral'