import type { Note, Comment, NotesQueryParams, CommentsQueryParams } from '../types'

/**
 * 爬虫数据 API
 */
export const useCrawlerDataApi = () => {
  const config = useRuntimeConfig()
  const baseURL = config.public.apiBase

  // ==================== 笔记相关 API ====================

  /**
   * 获取笔记列表
   */
  const getNotes = async (params?: NotesQueryParams) => {
    const query = new URLSearchParams()
    if (params?.skip !== undefined) query.append('skip', String(params.skip))
    if (params?.limit !== undefined) query.append('limit', String(params.limit))
    if (params?.platform) query.append('platform', params.platform)
    if (params?.author_id) query.append('author_id', params.author_id)
    if (params?.keyword) query.append('keyword', params.keyword)
    if (params?.start_date) query.append('start_date', params.start_date)
    if (params?.end_date) query.append('end_date', params.end_date)

    const queryString = query.toString()
    const url = `/api/v1/data/notes${queryString ? `?${queryString}` : ''}`

    return await $fetch<{ items: Note[], total: number }>(url, {
      baseURL,
      headers: useRequestHeaders(['cookie'])
    })
  }

  /**
   * 获取笔记详情
   */
  const getNote = async (id: number) => {
    return await $fetch<Note>(`/api/v1/data/notes/${id}`, {
      baseURL,
      headers: useRequestHeaders(['cookie'])
    })
  }

  /**
   * 根据平台和笔记ID获取笔记
   */
  const getNoteByPlatformId = async (platform: string, noteId: string) => {
    return await $fetch<Note>(`/api/v1/data/notes/by-platform/${platform}/${noteId}`, {
      baseURL,
      headers: useRequestHeaders(['cookie'])
    })
  }

  /**
   * 删除笔记
   */
  const deleteNote = async (id: number) => {
    return await $fetch(`/api/v1/data/notes/${id}`, {
      method: 'DELETE',
      baseURL,
      headers: useRequestHeaders(['cookie'])
    })
  }

  /**
   * 获取笔记总数
   */
  const getNotesCount = async (params?: { platform?: string }) => {
    const query = new URLSearchParams()
    if (params?.platform) query.append('platform', params.platform)

    const queryString = query.toString()
    const url = `/api/v1/data/notes/count${queryString ? `?${queryString}` : ''}`

    return await $fetch<{ count: number }>(url, {
      baseURL,
      headers: useRequestHeaders(['cookie'])
    })
  }

  // ==================== 评论相关 API ====================

  /**
   * 获取评论列表
   */
  const getComments = async (params?: CommentsQueryParams) => {
    const query = new URLSearchParams()
    if (params?.skip !== undefined) query.append('skip', String(params.skip))
    if (params?.limit !== undefined) query.append('limit', String(params.limit))
    if (params?.platform) query.append('platform', params.platform)
    if (params?.note_id) query.append('note_id', params.note_id)
    if (params?.author_id) query.append('author_id', params.author_id)
    if (params?.keyword) query.append('keyword', params.keyword)
    if (params?.start_date) query.append('start_date', params.start_date)
    if (params?.end_date) query.append('end_date', params.end_date)

    const queryString = query.toString()
    const url = `/api/v1/data/comments${queryString ? `?${queryString}` : ''}`

    return await $fetch<{ items: Comment[], total: number }>(url, {
      baseURL,
      headers: useRequestHeaders(['cookie'])
    })
  }

  /**
   * 获取评论详情
   */
  const getComment = async (id: number) => {
    return await $fetch<Comment>(`/api/v1/data/comments/${id}`, {
      baseURL,
      headers: useRequestHeaders(['cookie'])
    })
  }

  /**
   * 根据平台和评论ID获取评论
   */
  const getCommentByPlatformId = async (platform: string, commentId: string) => {
    return await $fetch<Comment>(`/api/v1/data/comments/by-platform/${platform}/${commentId}`, {
      baseURL,
      headers: useRequestHeaders(['cookie'])
    })
  }

  /**
   * 删除评论
   */
  const deleteComment = async (id: number) => {
    return await $fetch(`/api/v1/data/comments/${id}`, {
      method: 'DELETE',
      baseURL,
      headers: useRequestHeaders(['cookie'])
    })
  }

  /**
   * 获取评论总数
   */
  const getCommentsCount = async (params?: { platform?: string, note_id?: string }) => {
    const query = new URLSearchParams()
    if (params?.platform) query.append('platform', params.platform)
    if (params?.note_id) query.append('note_id', params.note_id)

    const queryString = query.toString()
    const url = `/api/v1/data/comments/count${queryString ? `?${queryString}` : ''}`

    return await $fetch<{ count: number }>(url, {
      baseURL,
      headers: useRequestHeaders(['cookie'])
    })
  }

  return {
    // 笔记
    getNotes,
    getNote,
    getNoteByPlatformId,
    deleteNote,
    getNotesCount,
    // 评论
    getComments,
    getComment,
    getCommentByPlatformId,
    deleteComment,
    getCommentsCount
  }
}
