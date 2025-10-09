import type {
  AccountCreatePayload,
  AccountListResponse,
  AccountResource,
  AccountUpdatePayload,
  ProxyCreatePayload,
  ProxyListResponse,
  ProxyResource,
  ProxyUpdatePayload,
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

  const getProxies = (params?: { active?: boolean }) =>
    useApiData<ProxyListResponse>('/resources/proxies', {
      query: params,
      key: computed(() => `crawler-proxies-${params?.active ?? 'all'}`),
    })

  const getProxy = (proxyId: number) =>
    useApiData<ProxyResource>(`/resources/proxies/${proxyId}`, {
      key: `crawler-proxy-${proxyId}`,
    })

  const createProxy = async (payload: ProxyCreatePayload) => {
    try {
      const result = await apiRequest<ProxyResource>('/resources/proxies', {
        method: 'POST',
        body: payload,
      })
      showSuccess('代理已创建')
      return result
    } catch (error) {
      showError('创建代理失败')
      throw error
    }
  }

  const updateProxy = async (proxyId: number, payload: ProxyUpdatePayload) => {
    try {
      const result = await apiRequest<ProxyResource>(`/resources/proxies/${proxyId}`, {
        method: 'PATCH',
        body: payload,
      })
      showSuccess('代理已更新')
      return result
    } catch (error) {
      showError('更新代理失败')
      throw error
    }
  }

  const updateProxyStatus = async (proxyId: number, isActive: boolean) => {
    try {
      const result = await apiRequest<ProxyResource>(`/resources/proxies/${proxyId}/status`, {
        method: 'PATCH',
        body: { is_active: isActive },
      })
      showSuccess(isActive ? '代理已启用' : '代理已禁用')
      return result
    } catch (error) {
      showError('更新代理状态失败')
      throw error
    }
  }

  return {
    getAccounts,
    getAccount,
    createAccount,
    updateAccount,
    updateAccountStatus,
    getProxies,
    getProxy,
    createProxy,
    updateProxy,
    updateProxyStatus,
  }
}
