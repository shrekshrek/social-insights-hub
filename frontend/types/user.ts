import type { PermissionWithMeta } from './permissions'

// 角色类型定义
export interface Role {
  id: number;
  name: string;
  display_name: string;
  description?: string;
  is_system: boolean;
  permission_strategy: 'all' | 'admin' | 'explicit';
  permissions?: PermissionWithMeta[]; // 可选的权限列表，用于角色详情展示
}

// 完整的用户模型（与后端 UserRead schema 同步）
export interface User {
  id: number;
  username: string;
  email: string | null;
  email_verified: boolean;
  oauth_provider?: string | null;
  avatar_url?: string | null;
  roles?: string[]; // 用户的角色名称数组（与后端一致）
  created_at: string; // ISO 8601 格式的时间字符串
  updated_at: string; // ISO 8601 格式的时间字符串
}

// 与后端 UserCreate schema 同步的用户创建类型（邀请制注册）
// 邮箱由 invite_token 决定，不在请求体中
export interface UserCreate {
  username: string;
  password: string;
  invite_token: string;
}

// 管理员创建用户时直接传 email + 可选角色 ID（不走邀请流程）
export interface AdminUserCreate {
  username: string;
  email?: string | null;
  password: string;
  role_ids?: number[];
}

// 管理员发送邀请的请求体
export interface InvitationCreateRequest {
  email: string;
  default_role_id?: number | null;
}

// 密码重置请求体
export interface ResetPasswordRequest {
  token: string;
  new_password: string;
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
