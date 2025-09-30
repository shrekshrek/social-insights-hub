import type { PermissionWithMeta } from './permissions'

// 角色类型定义
export interface Role {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  is_system: boolean;
  permissions?: PermissionWithMeta[]; // 可选的权限列表，用于角色详情展示
}

// 完整的用户模型（与后端 UserRead schema 同步）
export interface User {
  id: number;
  username: string;
  email: string;
  roles?: string[]; // 用户的角色名称数组（与后端一致）
  created_at: string; // ISO 8601 格式的时间字符串
  updated_at: string; // ISO 8601 格式的时间字符串
}

// 与后端 UserCreate schema 同步的用户创建类型
export interface UserCreate {
  username: string;
  email?: string | null; // 邮箱是可选的，与后端保持一致
  password: string;
}

// 管理员创建用户时可选携带角色ID
export interface AdminUserCreate extends UserCreate {
  role_ids?: number[];
}

// 用户更新类型
export interface UserUpdate {
  username?: string;
  email?: string | null; // 与UserCreate保持一致
  password?: string; // 密码在更新时是可选的
}

// 用户资料（用于前端状态管理，扩展了基础 User 类型）
export interface UserProfile extends User {
  roles: string[]; // UserProfile 确保 roles 总是存在
  // 前端扩展字段
  avatarUrl?: string | null;
}
