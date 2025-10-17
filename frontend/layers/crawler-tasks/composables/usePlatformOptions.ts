/**
 * 平台和爬取类型选项生成器
 * 统一管理所有下拉选项，避免重复代码和错误
 */
import { PLATFORM_LABELS, CRAWLER_TYPE_LABELS } from '../types'

export interface SelectOption {
  value: string
  label: string
}

/**
 * 获取平台选项（不含"全部"选项）
 */
export const usePlatformOptions = (): SelectOption[] => {
  return Object.entries(PLATFORM_LABELS).map(([value, label]) => ({
    value,
    label,
  }))
}

/**
 * 获取平台选项（筛选用，不含"全部"选项）
 * 注意：不包含"全部"选项，因为 SelectItem 不支持空字符串值
 * 使用 placeholder 和 undefined 来表示"全部"
 */
export const usePlatformOptionsWithAll = (): SelectOption[] => {
  return Object.entries(PLATFORM_LABELS).map(([value, label]) => ({
    value,
    label,
  }))
}

/**
 * 获取爬取类型选项（不含"全部"选项）
 */
export const useCrawlerTypeOptions = (): SelectOption[] => {
  return Object.entries(CRAWLER_TYPE_LABELS).map(([value, label]) => ({
    value,
    label,
  }))
}

/**
 * 获取爬取类型选项（含"全部"选项，用于筛选）
 */
export const useCrawlerTypeOptionsWithAll = (): SelectOption[] => {
  return [
    { value: '', label: '全部类型' },
    ...Object.entries(CRAWLER_TYPE_LABELS).map(([value, label]) => ({
      value,
      label,
    })),
  ]
}
