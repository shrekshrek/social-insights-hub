import type { JSONUploadData, JSONUploadResponse } from '../types'

export const useJSONUpload = () => {
  const { apiRequest, showSuccess, showError } = useApi()

  // 上传JSON数据
  const uploadJSONData = async (taskId: number, data: JSONUploadData) => {
    try {
      const result = await apiRequest<JSONUploadResponse>(`/tasks/${taskId}/upload`, {
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

      // 验证 contents 中每个帖子都有 post_id_on_platform
      for (let i = 0; i < data.contents.length; i++) {
        const post = data.contents[i]
        if (!post?.post_id_on_platform) {
          return { valid: false, error: `第 ${i + 1} 个帖子缺少 post_id_on_platform 字段` }
        }
      }

      // 验证 comments 中每个评论都有 comment_id_on_platform
      for (let i = 0; i < data.comments.length; i++) {
        const comment = data.comments[i]
        if (!comment?.comment_id_on_platform) {
          return { valid: false, error: `第 ${i + 1} 条评论缺少 comment_id_on_platform 字段` }
        }
      }

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
