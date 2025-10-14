import { computed } from 'vue'

import type {
  AccountCreatePayload,
  AccountListResponse,
  AccountResource,
  AccountUpdatePayload,
  ProxyPoolStatus,
  ProxyProvider,
  ProxyProviderCreatePayload,
  ProxyProviderListResponse,
  ProxyProviderUpdatePayload,
} from '../types'

export const useCrawlerResourcesApi = () => {
  const { apiRequest, useApiData, showSuccess, showError } = useApi()

  const getAccounts = (params?: { platform?: string; active?: boolean }) =>
    useApiData<AccountListResponse>('/resources/accounts', {
      query: params,
      key: computed(() => `crawler-accounts-${params?.platform ?? 'all'}-${params?.active ?? 'all'}`),
    })

  const getAccount = (accountId: number) =>
    useApiData<AccountResource>(`/resources/accounts/${accountId}`, {
      key: `crawler-account-${accountId}`,
    })

  const createAccount = async (payload: AccountCreatePayload) => {
    try {
      const result = await apiRequest<AccountResource>('/resources/accounts', {
        method: 'POST',
        body: payload,
      })
      showSuccess('账号已创建')
      return result
    } catch (error) {
      showError('创建账号失败')
      throw error
    }
  }

  const updateAccount = async (accountId: number, payload: AccountUpdatePayload) => {
    try {
      const result = await apiRequest<AccountResource>(`/resources/accounts/${accountId}`, {
        method: 'PATCH',
        body: payload,
      })
      showSuccess('账号已更新')
      return result
    } catch (error) {
      showError('更新账号失败')
      throw error
    }
  }

  const updateAccountStatus = async (accountId: number, isActive: boolean) => {
    try {
      const result = await apiRequest<AccountResource>(`/resources/accounts/${accountId}/status`, {
        method: 'PATCH',
        body: { is_active: isActive },
      })
      showSuccess(isActive ? '账号已启用' : '账号已禁用')
      return result
    } catch (error) {
      showError('更新账号状态失败')
      throw error
    }
  }

  const getProxyProviders = (params?: { active?: boolean }) =>
    useApiData<ProxyProviderListResponse>('/resources/proxy-providers', {
      query: params,
      key: computed(() => `crawler-proxy-providers-${params?.active ?? 'all'}`),
    })

  const getProxyProvider = (providerId: number) =>
    useApiData<ProxyProvider>(`/resources/proxy-providers/${providerId}`, {
      key: `crawler-proxy-provider-${providerId}`,
    })

  const createProxyProvider = async (payload: ProxyProviderCreatePayload) => {
    try {
      const result = await apiRequest<ProxyProvider>('/resources/proxy-providers', {
        method: 'POST',
        body: payload,
      })
      showSuccess('代理服务商配置已创建')
      return result
    } catch (error) {
      showError('创建代理服务商配置失败')
      throw error
    }
  }

  const updateProxyProvider = async (providerId: number, payload: ProxyProviderUpdatePayload) => {
    try {
      const result = await apiRequest<ProxyProvider>(`/resources/proxy-providers/${providerId}`, {
        method: 'PATCH',
        body: payload,
      })
      showSuccess('代理服务商配置已更新')
      return result
    } catch (error) {
      showError('更新代理服务商配置失败')
      throw error
    }
  }

  const refreshProxyProvider = async (providerId: number) => {
    try {
      const result = await apiRequest<ProxyPoolStatus>(
        `/resources/proxy-providers/${providerId}/refresh`,
        {
          method: 'POST',
        },
      )
      showSuccess('代理池已刷新')
      return result
    } catch (error) {
      showError('刷新代理池失败')
      throw error
    }
  }

  const getProxyPoolStatus = async (providerId: number) => {
    try {
      return await apiRequest<ProxyPoolStatus>(
        `/resources/proxy-providers/${providerId}/status`,
      )
    } catch (error) {
      showError('获取代理池状态失败')
      throw error
    }
  }

  return {
    getAccounts,
    getAccount,
    createAccount,
    updateAccount,
    updateAccountStatus,
    getProxyProviders,
    getProxyProvider,
    createProxyProvider,
    updateProxyProvider,
    refreshProxyProvider,
    getProxyPoolStatus,
  }
}
