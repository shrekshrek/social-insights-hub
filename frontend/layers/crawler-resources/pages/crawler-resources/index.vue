<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">资源管理</h1>
        <p class="text-gray-500">维护账号与代理资源，支持启用/禁用及基础编辑。</p>
      </div>
      <div class="flex items-center gap-2">
        <UButton icon="i-heroicons-plus" @click="openAccountModal()">新增账号</UButton>
        <UButton icon="i-heroicons-plus" variant="outline" @click="openProxyModal()">新增代理</UButton>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <UButton
        :variant="activeTab === 'account' ? 'solid' : 'ghost'"
        @click="activeTab = 'account'"
      >
        账号
      </UButton>
      <UButton
        :variant="activeTab === 'proxy' ? 'solid' : 'ghost'"
        @click="activeTab = 'proxy'"
      >
        代理
      </UButton>
    </div>

    <ResourceList
      v-if="activeTab === 'account'"
      type="account"
      :loading="accountsPending"
      :items="accounts"
      @refresh="refreshAccounts"
      @edit="item => openAccountModal(item as AccountResource)"
      @toggle="item => toggleAccount(item as AccountResource)"
    />
    <ResourceList
      v-else
      type="proxy"
      :loading="proxiesPending"
      :items="proxies"
      @refresh="refreshProxies"
      @edit="item => openProxyModal(item as ProxyResource)"
      @toggle="item => toggleProxy(item as ProxyResource)"
    />

    <AccountModal
      v-if="showAccountModal"
      v-model:open="showAccountModal"
      :editing="editingAccount"
      :loading="accountSaving"
      @submit="handleAccountSubmit"
    />
    <ProxyModal
      v-if="showProxyModal"
      v-model:open="showProxyModal"
      :editing="editingProxy"
      :loading="proxySaving"
      @submit="handleProxySubmit"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useCrawlerResourcesApi } from '../../composables/useCrawlerResourcesApi'
import ResourceList from '../../components/ResourceList.vue'
import AccountModal from '../../components/AccountModal.vue'
import ProxyModal from '../../components/ProxyModal.vue'
import type { AccountResource, ProxyResource, AccountCreatePayload, AccountUpdatePayload, ProxyCreatePayload, ProxyUpdatePayload } from '../../types'

const activeTab = ref<'account' | 'proxy'>('account')

const showAccountModal = ref(false)
const showProxyModal = ref(false)
const editingAccount = ref<AccountResource | null>(null)
const editingProxy = ref<ProxyResource | null>(null)
const accountSaving = ref(false)
const proxySaving = ref(false)

const resourcesApi = useCrawlerResourcesApi()

const {
  data: accountData,
  pending: accountsPending,
  refresh: refreshAccounts,
} = await resourcesApi.getAccounts()

const {
  data: proxyData,
  pending: proxiesPending,
  refresh: refreshProxies,
} = await resourcesApi.getProxies()

const accounts = computed(() => accountData.value ?? [])
const proxies = computed(() => proxyData.value ?? [])

const openAccountModal = (account?: AccountResource) => {
  editingAccount.value = account ?? null
  showAccountModal.value = true
}

const openProxyModal = (proxy?: ProxyResource) => {
  editingProxy.value = proxy ?? null
  showProxyModal.value = true
}

const handleAccountSubmit = async (payload: AccountCreatePayload | AccountUpdatePayload, accountId?: number) => {
  accountSaving.value = true
  try {
    if (accountId) {
      await resourcesApi.updateAccount(accountId, payload)
    } else {
      await resourcesApi.createAccount(payload as AccountCreatePayload)
    }
    await refreshAccounts()
    showAccountModal.value = false
    editingAccount.value = null
  } finally {
    accountSaving.value = false
  }
}

const handleProxySubmit = async (payload: ProxyCreatePayload | ProxyUpdatePayload, proxyId?: number) => {
  proxySaving.value = true
  try {
    if (proxyId) {
      await resourcesApi.updateProxy(proxyId, payload)
    } else {
      await resourcesApi.createProxy(payload as ProxyCreatePayload)
    }
    await refreshProxies()
    showProxyModal.value = false
    editingProxy.value = null
  } finally {
    proxySaving.value = false
  }
}

const toggleAccount = async (account: AccountResource) => {
  await resourcesApi.updateAccountStatus(account.id, !account.is_active)
  await refreshAccounts()
}

const toggleProxy = async (proxy: ProxyResource) => {
  await resourcesApi.updateProxyStatus(proxy.id, !proxy.is_active)
  await refreshProxies()
}
</script>
