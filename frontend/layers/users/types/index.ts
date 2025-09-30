// 重新导出核心用户类型（来自根级别类型定义）
export type { User, UserCreate, UserUpdate, Role, AdminUserCreate } from '../../../types/user'

// 重新导出通用类型（来自根级别类型定义）
export type { PaginationParams, UIColor } from '../../../types/common'

// 用户管理模块特有的响应类型
export interface UserListResponse {
  items: User[];
  total: number;
  page: number;
  page_size: number;
}

// 用户管理模块的特定类型可以在这里定义 
