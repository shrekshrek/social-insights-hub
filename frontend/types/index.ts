// 统一导出所有类型定义，方便其他模块导入

// 认证相关类型
export type {
  Token,
  TokenData,
  PasswordResetRequest,
  PasswordReset,
  MessageResponse,
  LoginRequest,
  RegisterRequest,
  AuthStatus,
  ApiResponse,
  ApiError,
} from './auth'

// 用户相关类型
export type {
  Role,
  User,
  UserCreate,
  UserUpdate,
  UserProfile,
} from './user'

// 通用类型
export type {
  PaginationParams,
  PaginatedResponse,
  FormErrors,
  LoadingState,
  OperationResult,
  UIColor,
} from './common'