import type { Platform } from '../../tasks/types'

export const usePlatforms = () => {
  const { useApiData } = useApi()

  // 获取所有平台列表
  const getPlatforms = () => {
    return useApiData<Platform[]>('/social-media/platforms', {
      key: 'platforms-list',
    })
  }

  // 获取单个平台
  const getPlatform = (id: number) => {
    return useApiData<Platform>(`/social-media/platforms/${id}`, {
      key: `platform-${id}`,
    })
  }

  return {
    getPlatforms,
    getPlatform,
  }
}
