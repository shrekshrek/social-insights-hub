import type {
  SocialPostWithComments,
  PostQueryResponse,
  PostListResponse,
  CommentListResponse,
} from '../types'

export const usePosts = () => {
  const { useApiData } = useApi()

  // 获取任务的原文列表
  const getTaskPosts = (taskId: number, params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<PostListResponse>(`/social-media/tasks/${taskId}/posts`, {
      query: params,
      key: computed(() => {
        const p = unref(params)
        return `task-${taskId}-posts-${p?.page || 1}-${p?.page_size || 20}-${p?.post_id || 'all'}`
      }),
    })
  }

  // 获取任务的评论列表
  const getTaskComments = (taskId: number, params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<CommentListResponse>(`/social-media/tasks/${taskId}/comments`, {
      query: params,
      key: computed(() => {
        const p = unref(params)
        return `task-${taskId}-comments-${p?.page || 1}-${p?.page_size || 50}-${p?.post_id || 'all'}`
      }),
    })
  }

  // 获取原文及其评论
  const getPostWithComments = (postId: number, params?: MaybeRef<Record<string, unknown>>) => {
    return useApiData<SocialPostWithComments>(`/social-media/tasks/posts/${postId}`, {
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
      `/social-media/tasks/posts/cross-task/${platformId}/${postIdOnPlatform}`,
      {
        query: params,
        key: `cross-task-${platformId}-${postIdOnPlatform}-${params?.project_id || ''}`,
      }
    )
  }

  return {
    getTaskPosts,
    getTaskComments,
    getPostWithComments,
    queryCrossTaskPosts,
  }
}
