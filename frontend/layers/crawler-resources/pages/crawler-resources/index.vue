<template>
  <div class="space-y-6">
    <!-- 页面标题和操作按钮 -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div class="space-y-1">
        <h1 class="text-2xl font-bold">资源管理</h1>
        <p class="text-gray-500">维护账号与代理资源，支持启用/禁用、编辑与筛选。</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <UButton icon="i-heroicons-plus" color="primary" @click="openAccountModal()">
          新增账号
        </UButton>
        <UButton icon="i-heroicons-plus" variant="outline" @click="openProviderModal()">
          新增代理服务商
        </UButton>
        <UButton icon="i-heroicons-arrow-path" variant="ghost" @click="handleRefreshAll">
          刷新
        </UButton>
      </div>
    </div>

    <!-- 账号资源 -->
    <UCard>
      <template #header>
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div class="flex items-center gap-2">
            <h2 class="text-xl font-semibold">账号资源</h2>
            <UBadge color="primary" variant="soft">{{ accountsTotal }}</UBadge>
            <UBadge color="success" variant="soft">启用 {{ accountsActive }}/{{ accountsTotal }}</UBadge>
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
        </div>
      </template>

      <ResourceList
        type="account"
        :loading="accountsPending"
        :items="filteredAccounts"
        @edit="item => openAccountModal(item as AccountResource)"
        @toggle="item => toggleAccount(item as AccountResource)"
      />
    </UCard>

    <!-- 代理服务商 -->
    <UCard>
      <template #header>
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div class="flex items-center gap-2">
            <h2 class="text-xl font-semibold">代理服务商</h2>
            <UBadge color="primary" variant="soft">{{ providersTotal }}</UBadge>
            <UBadge color="success" variant="soft">启用 {{ providersActive }}/{{ providersTotal }}</UBadge>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <USelect
              v-model="providerFilters.active"
              :items="activeOptions"
              placeholder="全部状态"
              value-attribute="value"
              label-attribute="label"
              clearable
              class="w-32"
            />
            <UInput
              v-model="providerFilters.keyword"
              placeholder="搜索配置名称..."
              icon="i-heroicons-magnifying-glass"
              class="w-48"
            />
          </div>
        </div>
      </template>

      <ResourceList
        type="provider"
        :loading="providersPending"
        :items="filteredProviders"
        @edit="item => openProviderModal(item as ProxyProvider)"
        @toggle="item => toggleProvider(item as ProxyProvider)"
        @refresh="item => refreshProviderPool(item as ProxyProvider)"
      />
    </UCard>

    <!-- 模态框 -->
    <AccountModal
      v-if="showAccountModal"
      v-model:open="showAccountModal"
      :editing="editingAccount"
      :loading="accountSaving"
      @submit="(payload, id) => handleAccountSubmit(payload as AccountCreatePayload | AccountUpdatePayload, id)"
    />
    <ProxyProviderModal
      v-if="showProviderModal"
      v-model:open="showProviderModal"
      :editing="editingProvider"
      :loading="providerSaving"
      @submit="(payload, id) => handleProviderSubmit(payload as ProxyProviderCreatePayload | ProxyProviderUpdatePayload, id)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useCrawlerResourcesApi } from '../../composables/useCrawlerResourcesApi'
import ResourceList from '../../components/ResourceList.vue'
import AccountModal from '../../components/AccountModal.vue'
import ProxyProviderModal from '../../components/ProxyProviderModal.vue'
import type {
  AccountResource,
  ProxyProvider,
  AccountCreatePayload,
  AccountUpdatePayload,
  ProxyProviderCreatePayload,
  ProxyProviderUpdatePayload,
} from '../../types'

const showAccountModal = ref(false)
const showProviderModal = ref(false)
const editingAccount = ref<AccountResource | null>(null)
const editingProvider = ref<ProxyProvider | null>(null)
const accountSaving = ref(false)
const providerSaving = ref(false)

const accountFilters = reactive({
  platform: 'all' as 'all' | string,
  active: 'all' as 'all' | 'active' | 'inactive',
  keyword: '',
})

const providerFilters = reactive({
  active: 'all' as 'all' | 'active' | 'inactive',
  keyword: '',
})

watch(
  () => accountFilters.platform,
  (value) => {
    if (!value) {
      accountFilters.platform = 'all'
    }
  },
)

watch(
  () => accountFilters.active,
  (value) => {
    if (!value) {
      accountFilters.active = 'all'
    }
  },
)

watch(
  () => providerFilters.active,
  (value) => {
    if (!value) {
      providerFilters.active = 'all'
    }
  },
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
const {
  data: providerData,
  pending: providersPending,
  refresh: refreshProviders,
} = await resourcesApi.getProxyProviders()

const accounts = computed(() => accountData.value ?? [])
const providers = computed(() => providerData.value ?? [])

const accountsTotal = computed(() => accounts.value.length)
const providersTotal = computed(() => providers.value.length)
const accountsActive = computed(() => accounts.value.filter((item) => item.is_active).length)
const providersActive = computed(() => providers.value.filter((item) => item.is_active).length)

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

const filteredProviders = computed(() =>
  providers.value.filter((item) => {
    const matchesStatus = providerFilters.active !== 'all'
      ? providerFilters.active === 'active'
        ? item.is_active
        : !item.is_active
      : true
    const matchesKeyword = providerFilters.keyword
      ? item.name.toLowerCase().includes(providerFilters.keyword.toLowerCase())
      : true
    return matchesStatus && matchesKeyword
  }),
)

function openAccountModal(account?: AccountResource) {
  editingAccount.value = account ?? null
  showAccountModal.value = true
}

function openProviderModal(provider?: ProxyProvider) {
  editingProvider.value = provider ?? null
  showProviderModal.value = true
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

async function handleProviderSubmit(
  payload: ProxyProviderCreatePayload | ProxyProviderUpdatePayload,
  providerId?: number,
) {
  providerSaving.value = true
  try {
    if (providerId) {
      await resourcesApi.updateProxyProvider(providerId, payload)
    } else {
      await resourcesApi.createProxyProvider(payload as ProxyProviderCreatePayload)
    }
    await refreshProviders()
    showProviderModal.value = false
    editingProvider.value = null
  } finally {
    providerSaving.value = false
  }
}

async function toggleAccount(account: AccountResource) {
  await resourcesApi.updateAccountStatus(account.id, !account.is_active)
  await refreshAccounts()
}

async function toggleProvider(provider: ProxyProvider) {
  await resourcesApi.updateProxyProvider(provider.id, { is_active: !provider.is_active })
  await refreshProviders()
}

async function refreshProviderPool(provider: ProxyProvider) {
  await resourcesApi.refreshProxyProvider(provider.id)
  await refreshProviders()
}

async function handleRefreshAll() {
  await Promise.all([refreshAccounts(), refreshProviders()])
}
</script>
