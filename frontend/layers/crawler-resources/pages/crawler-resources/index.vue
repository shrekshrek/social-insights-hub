<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div class="space-y-1">
        <h1 class="text-2xl font-bold">资源管理</h1>
        <p class="text-gray-500">维护账号与代理资源，支持启用/禁用、编辑与筛选。</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <UButton icon="i-heroicons-plus" color="primary" @click="openAccountModal()">
          新增账号
        </UButton>
        <UButton icon="i-heroicons-plus" variant="outline" @click="openProxyModal()">
          新增代理
        </UButton>
        <UButton icon="i-heroicons-arrow-path" variant="ghost" @click="handleRefreshAll">
          刷新
        </UButton>
      </div>
    </div>

    <div class="grid grid-cols-1 gap-6 xl:grid-cols-2">
      <UCard>
        <div class="space-y-1">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-xl font-semibold">账号资源</h2>
            <UBadge color="primary" variant="soft">{{ accountsTotal }}</UBadge>
            <UBadge color="success" variant="soft">启用 {{ accountsActive }}/{{ accountsTotal }}</UBadge>
          </div>
          <p class="text-sm text-gray-500">按平台与状态筛选账号，快速定位与管理。</p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <USelect
            v-model="accountFilters.platform"
            :items="platformSelectOptions"
            placeholder="全部平台"
            value-attribute="value"
            label-attribute="label"
            clearable
            class="w-36"
          />
          <USelect
            v-model="accountFilters.active"
            :items="activeOptions"
            placeholder="全部状态"
            value-attribute="value"
            label-attribute="label"
            clearable
            class="w-32"
          />
          <UInput
            v-model="accountFilters.keyword"
            placeholder="搜索账号..."
            icon="i-heroicons-magnifying-glass"
            class="w-48"
          />
        </div>

        <ResourceList
          type="account"
          :loading="accountsPending"
          :items="filteredAccounts"
          @edit="item => openAccountModal(item as AccountResource)"
          @toggle="item => toggleAccount(item as AccountResource)"
        />
      </UCard>

      <UCard>
        <div class="space-y-1">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-xl font-semibold">代理资源</h2>
            <UBadge color="primary" variant="soft">{{ proxiesTotal }}</UBadge>
            <UBadge color="success" variant="soft">启用 {{ proxiesActive }}/{{ proxiesTotal }}</UBadge>
          </div>
          <p class="text-sm text-gray-500">维护代理节点配置，掌握可用率与健康度。</p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <USelect
            v-model="proxyFilters.active"
            :items="activeOptions"
            placeholder="全部状态"
            value-attribute="value"
            label-attribute="label"
            clearable
            class="w-32"
          />
          <UInput
            v-model="proxyFilters.keyword"
            placeholder="搜索代理地址..."
            icon="i-heroicons-magnifying-glass"
            class="w-48"
          />
        </div>

        <ResourceList
          type="proxy"
          :loading="proxiesPending"
          :items="filteredProxies"
          @edit="item => openProxyModal(item as ProxyResource)"
          @toggle="item => toggleProxy(item as ProxyResource)"
        />
      </UCard>
    </div>

    <AccountModal
      v-if="showAccountModal"
      v-model:open="showAccountModal"
      :editing="editingAccount"
      :loading="accountSaving"
      @submit="(payload, id) => handleAccountSubmit(payload as AccountCreatePayload | AccountUpdatePayload, id)"
    />
    <ProxyModal
      v-if="showProxyModal"
      v-model:open="showProxyModal"
      :editing="editingProxy"
      :loading="proxySaving"
      @submit="(payload, id) => handleProxySubmit(payload as ProxyCreatePayload | ProxyUpdatePayload, id)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useCrawlerResourcesApi } from '../../composables/useCrawlerResourcesApi'
import ResourceList from '../../components/ResourceList.vue'
import AccountModal from '../../components/AccountModal.vue'
import ProxyModal from '../../components/ProxyModal.vue'
import type {
  AccountResource,
  ProxyResource,
  AccountCreatePayload,
  AccountUpdatePayload,
  ProxyCreatePayload,
  ProxyUpdatePayload,
} from '../../types'

const showAccountModal = ref(false)
const showProxyModal = ref(false)
const editingAccount = ref<AccountResource | null>(null)
const editingProxy = ref<ProxyResource | null>(null)
const accountSaving = ref(false)
const proxySaving = ref(false)

const accountFilters = reactive({
  platform: 'all' as 'all' | string,
  active: 'all' as 'all' | 'active' | 'inactive',
  keyword: '',
})

const proxyFilters = reactive({
  active: 'all' as 'all' | 'active' | 'inactive',
  keyword: '',
})

watch(
  () => accountFilters.platform,
  (value) => {
    if (!value) {
      accountFilters.platform = 'all'
    }
  }
)

watch(
  () => accountFilters.active,
  (value) => {
    if (!value) {
      accountFilters.active = 'all'
    }
  }
)

watch(
  () => proxyFilters.active,
  (value) => {
    if (!value) {
      proxyFilters.active = 'all'
    }
  }
)

const platformSelectOptions = computed(() => [
  { label: '全部平台', value: 'all' },
  { label: '小红书', value: 'xhs' },
  { label: '微博', value: 'weibo' },
  { label: '抖音', value: 'douyin' },
  { label: '快手', value: 'kuaishou' },
  { label: '哔哩哔哩', value: 'bilibili' },
  { label: '贴吧', value: 'tieba' },
  { label: '知乎', value: 'zhihu' },
])

const activeOptions = computed(() => [
  { label: '全部状态', value: 'all' },
  { label: '仅启用', value: 'active' },
  { label: '仅停用', value: 'inactive' },
])

const resourcesApi = useCrawlerResourcesApi()

const { data: accountData, pending: accountsPending, refresh: refreshAccounts } = await resourcesApi.getAccounts()
const { data: proxyData, pending: proxiesPending, refresh: refreshProxies } = await resourcesApi.getProxies()

const accounts = computed(() => accountData.value ?? [])
const proxies = computed(() => proxyData.value ?? [])

const accountsTotal = computed(() => accounts.value.length)
const proxiesTotal = computed(() => proxies.value.length)
const accountsActive = computed(() => accounts.value.filter((item) => item.is_active).length)
const proxiesActive = computed(() => proxies.value.filter((item) => item.is_active).length)

const filteredAccounts = computed(() =>
  accounts.value.filter((item) => {
    const matchesPlatform = accountFilters.platform !== 'all' ? item.platform === accountFilters.platform : true
    const matchesStatus = accountFilters.active !== 'all'
      ? accountFilters.active === 'active'
        ? item.is_active
        : !item.is_active
      : true
    const matchesKeyword = accountFilters.keyword
      ? item.account_name.toLowerCase().includes(accountFilters.keyword.toLowerCase())
      : true
    return matchesPlatform && matchesStatus && matchesKeyword
  }),
)

const filteredProxies = computed(() =>
  proxies.value.filter((item) => {
    const matchesStatus = proxyFilters.active !== 'all'
      ? proxyFilters.active === 'active'
        ? item.is_active
        : !item.is_active
      : true
    const matchesKeyword = proxyFilters.keyword
      ? `${item.host}:${item.port}`.toLowerCase().includes(proxyFilters.keyword.toLowerCase())
      : true
    return matchesStatus && matchesKeyword
  }),
)

function openAccountModal(account?: AccountResource) {
  editingAccount.value = account ?? null
  showAccountModal.value = true
}

function openProxyModal(proxy?: ProxyResource) {
  editingProxy.value = proxy ?? null
  showProxyModal.value = true
}

async function handleAccountSubmit(payload: AccountCreatePayload | AccountUpdatePayload, accountId?: number) {
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

async function handleProxySubmit(payload: ProxyCreatePayload | ProxyUpdatePayload, proxyId?: number) {
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

async function toggleAccount(account: AccountResource) {
  await resourcesApi.updateAccountStatus(account.id, !account.is_active)
  await refreshAccounts()
}

async function toggleProxy(proxy: ProxyResource) {
  await resourcesApi.updateProxyStatus(proxy.id, !proxy.is_active)
  await refreshProxies()
}

async function handleRefreshAll() {
  await Promise.all([refreshAccounts(), refreshProxies()])
}
</script>
