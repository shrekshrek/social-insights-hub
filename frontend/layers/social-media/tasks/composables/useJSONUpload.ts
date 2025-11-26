import type { JSONUploadData, JSONUploadResponse } from '../types'

export const useJSONUpload = () => {
  const { apiRequest, showSuccess, showError } = useApi()

  // 上传JSON数据
  const uploadJSONData = async (taskId: number, data: JSONUploadData) => {
    try {
      const result = await apiRequest<JSONUploadResponse>(`/social-media/tasks/${taskId}/upload`, {
        method: 'POST',
        body: data,
      })
      showSuccess(`数据上传成功！导入了 ${result.posts_imported} 个帖子和 ${result.comments_imported} 条评论`)
      return result
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : '数据上传失败'
      showError(message)
      throw error
    }
  }

  // 验证JSON数据格式
  // 注意：后端适配器会处理字段映射，前端只需验证基本结构
  const validateJSONData = (jsonStr: string): { valid: boolean; data?: JSONUploadData; error?: string } => {
    try {
      const data = JSON.parse(jsonStr) as JSONUploadData

      // 验证必需字段
      if (!data.contents || !Array.isArray(data.contents)) {
        return { valid: false, error: '缺少 contents 字段或格式不正确' }
      }

      if (!data.comments || !Array.isArray(data.comments)) {
        return { valid: false, error: '缺少 comments 字段或格式不正确' }
      }

      // 验证 contents 不为空
      if (data.contents.length === 0) {
        return { valid: false, error: 'contents 数组不能为空' }
      }

      // 注意：不再验证具体字段名（如 post_id_on_platform）
      // 后端适配器会根据平台自动转换原始字段名

      return { valid: true, data }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : '未知错误'
      return { valid: false, error: `JSON 解析失败: ${message}` }
    }
  }

  return {
    uploadJSONData,
    validateJSONData,
  }
}
