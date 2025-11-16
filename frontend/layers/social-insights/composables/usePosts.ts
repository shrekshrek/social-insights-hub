import type {
  SocialPost,
  SocialPostWithComments,
  PostQueryResponse,
} from '../types'

export const usePosts = () => {
  const { useApiData } = useApi()

  // 获取任务的原文列表
  const getTaskPosts = (taskId: number, params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<SocialPost[]>(`/tasks/${taskId}/posts`, {
      query: params,
      key: computed(() => {
        const p = unref(params)
        return `task-${taskId}-posts-${p?.page || 1}-${p?.page_size || 20}`
      }),
    })
  }

  // 获取原文及其评论
  const getPostWithComments = (postId: number, params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<SocialPostWithComments>(`/tasks/posts/${postId}`, {
      query: params,
      key: computed(() => {
        const p = unref(params)
        return `post-${postId}-comments-${p?.page || 1}-${p?.page_size || 50}`
      }),
    })
  }

  // 跨任务查询同一帖子
  const queryCrossTaskPosts = (
    platformId: number,
    postIdOnPlatform: string,
    params?: Record<string, unknown>
  ) => {
    return useApiData<PostQueryResponse>(
      `/tasks/posts/cross-task/${platformId}/${postIdOnPlatform}`,
      {
        query: params,
        key: `cross-task-${platformId}-${postIdOnPlatform}-${params?.project_id || ''}`,
      }
    )
  }

  return {
    getTaskPosts,
    getPostWithComments,
    queryCrossTaskPosts,
  }
}
