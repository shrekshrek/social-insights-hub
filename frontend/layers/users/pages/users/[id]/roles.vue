<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">编辑用户角色</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          为用户 "{{ user?.username }}" 分配角色
        </p>
      </div>
      
      <div class="flex items-center gap-3">
        <UButton
          icon="i-heroicons-arrow-left"
          variant="outline"
          size="sm"
          @click="handleCancel"
        >
          返回
        </UButton>
      </div>
    </div>

    <!-- 用户信息卡片 -->
    <UCard v-if="user">
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">用户信息</h2>
          <div class="flex flex-wrap gap-1">
            <UBadge
              v-for="role in user.roles"
              :key="role"
              :color="getRoleColor(role)"
              variant="soft"
              size="sm"
            >
              {{ getRoleLabel(role) }}
            </UBadge>
          </div>
        </div>
      </template>

      <div class="flex items-center gap-3 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <UAvatar
          :alt="user.username"
          size="md"
        >
          {{ user.username.charAt(0).toUpperCase() }}
        </UAvatar>
        <div>
          <p class="font-medium text-gray-900 dark:text-white">{{ user.username }}</p>
          <p class="text-sm text-gray-500 dark:text-gray-400">{{ user.email }}</p>
        </div>
      </div>
    </UCard>

    <!-- 角色分配卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold">角色分配</h2>
          </div>
                      <div class="flex items-center gap-3">
              <ClientOnly>
                <div class="flex items-center gap-2">
                  <span class="text-sm text-gray-500 dark:text-gray-400">
                    已选择 {{ selectedRoleIds.length }} 个角色
                  </span>
                  <span v-if="selectedRoleIds.length === 0" class="text-xs text-amber-600 dark:text-amber-400">
                    (用户至少需要一个角色)
                  </span>
                </div>
              </ClientOnly>
              <UInput
                v-model="searchQuery"
                placeholder="搜索角色..."
                icon="i-heroicons-magnifying-glass"
                size="sm"
                class="w-64"
              />
            </div>
        </div>
      </template>

      <!-- 加载状态 -->
      <div v-if="rolesLoading" class="space-y-4">
        <div v-for="i in 6" :key="i" class="animate-pulse">
          <div class="h-20 bg-gray-200 dark:bg-gray-700 rounded-lg"/>
        </div>
      </div>

      <!-- 角色列表 -->
      <ClientOnly>
        <template #fallback>
          <div class="space-y-4">
            <div v-for="i in 6" :key="i" class="animate-pulse">
              <div class="h-20 bg-gray-200 dark:bg-gray-700 rounded-lg"/>
            </div>
          </div>
        </template>

        <div v-if="!rolesLoading && filteredRoles.length > 0" class="space-y-4">
          <!-- 按系统/自定义分组 -->
          <div
            v-for="group in roleGroups"
            :key="group.type"
            class="border border-gray-200 dark:border-gray-700 rounded-lg p-4"
          >
            <div class="flex items-center justify-between mb-3">
              <h3 class="font-medium text-gray-900 dark:text-white">
                {{ group.label }} ({{ group.roles.length }} 个)
              </h3>
              <div class="flex items-center gap-2">
                <UButton
                  size="xs"
                  variant="outline"
                  :disabled="loading"
                  @click="selectAllInGroup(group.type)"
                >
                  全选
                </UButton>
                <UButton
                  size="xs"
                  variant="outline"
                  color="neutral"
                  :disabled="loading"
                  @click="deselectAllInGroup(group.type)"
                >
                  取消全选
                </UButton>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
              <div
                v-for="role in group.roles"
                :key="role.id"
                class="flex items-center gap-3 p-2 hover:bg-gray-50 dark:hover:bg-gray-800 rounded transition-colors"
              >
                <UCheckbox
                  v-model="getRoleModel(role.id).value"
                  :disabled="loading"
                />
                <div class="flex-1 min-w-0">
                  <div class="flex items-center justify-between">
                    <p class="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {{ role.display_name }}
                    </p>
                    <UBadge
                      :color="isCoreRole(role.name) ? 'warning' : 'neutral'"
                      variant="soft"
                      size="sm"
                    >
                      {{ isCoreRole(role.name) ? '核心' : '自定义' }}
                    </UBadge>
                  </div>
                  <p class="text-xs text-gray-500 dark:text-gray-400 truncate">
                    {{ role.description || '暂无描述' }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 无角色状态 -->
        <div v-else-if="!rolesLoading && filteredRoles.length === 0" class="text-center py-12">
          <div class="w-16 h-16 mx-auto mb-4 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center">
            <UIcon name="i-heroicons-user-group" class="w-8 h-8 text-gray-400" />
          </div>
          <p class="text-gray-500 dark:text-gray-400">
            {{ searchQuery ? '未找到匹配的角色' : '暂无可分配的角色' }}
          </p>
        </div>
      </ClientOnly>

      <!-- 操作按钮 -->
      <template #footer>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <UButton
              variant="outline"
              size="sm"
              :disabled="loading"
              @click="resetSelection"
            >
              重置选择
            </UButton>
          </div>
          
          <div class="flex items-center gap-3">
            <UButton
              variant="outline"
              :disabled="loading"
              @click="handleCancel"
            >
              取消
            </UButton>
            <UButton
              color="primary"
              :loading="loading"
              :disabled="!hasChanges"
              @click="handleSubmit"
            >
              保存更改
            </UButton>
          </div>
        </div>
      </template>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import type { User } from '../../../types'
import { getRoleColor, getRoleLabel } from '../../../utils/ui-helpers'
import { isCoreRole } from '../../../../rbac/utils/permissions'  // 明确的跨模块依赖

// 页面元数据
definePageMeta({
  title: '编辑用户角色',
  description: '为用户分配角色'
})

// 路由参数
const route = useRoute()
const userId = computed(() => Number(route.params.id))

// 响应式数据
const user = ref<User | null>(null)
const selectedRoleIds = ref<number[]>([])
const searchQuery = ref('')
const loading = ref(false)

// API
const usersApi = useUsersApi()
const rbacApi = useRbacApi()

// 获取用户数据
const { data: userData } = usersApi.getUser(userId.value)

// 获取所有角色
const { data: rolesData, pending: rolesLoading } = rbacApi.getRoles({})

// 计算属性
const availableRoles = computed(() => {
  return rolesData.value?.items || []
})

const filteredRoles = computed(() => {
  if (!searchQuery.value) return availableRoles.value
  
  const query = searchQuery.value.toLowerCase()
  return availableRoles.value.filter(role =>
    role.display_name.toLowerCase().includes(query) ||
    role.name.toLowerCase().includes(query) ||
    (role.description && role.description.toLowerCase().includes(query))
  )
})

const roleGroups = computed(() => {
  const systemRoles = filteredRoles.value.filter(role => isCoreRole(role.name))
  const customRoles = filteredRoles.value.filter(role => !isCoreRole(role.name))
  
  const groups = []
  
  if (systemRoles.length > 0) {
    groups.push({
      type: 'system',
      label: '系统角色',
      roles: systemRoles
    })
  }
  
  if (customRoles.length > 0) {
    groups.push({
      type: 'custom',
      label: '自定义角色',
      roles: customRoles
    })
  }
  
  return groups
})

// 获取默认角色（普通用户）
const getDefaultRole = () => {
  return availableRoles.value.find(role => role.name === 'user')
}

// 检查是否至少选择了一个角色
const hasAtLeastOneRole = computed(() => {
  return selectedRoleIds.value.length > 0
})

// 检查是否有变更
const hasChanges = computed(() => {
  const originalRoleNames = user.value?.roles || []
  const originalRoleIds = availableRoles.value
    .filter(role => originalRoleNames.includes(role.name))
    .map(role => role.id)
    .sort()
  
  const currentIds = [...selectedRoleIds.value].sort()
  
  if (originalRoleIds.length !== currentIds.length) return true
  
  return originalRoleIds.some((id, index) => id !== currentIds[index])
})

// 初始化用户数据
watch(userData, (newUser) => {
  if (newUser) {
    user.value = newUser
  }
}, { immediate: true })

// 初始化选中的角色
const initializeSelectedRoles = () => {
  if (!user.value || !availableRoles.value.length) return
  
  const userRoleNames = user.value.roles || []
  const roleIds: number[] = []
  
  availableRoles.value.forEach(role => {
    if (userRoleNames.includes(role.name)) {
      roleIds.push(role.id)
    }
  })
  
  selectedRoleIds.value = roleIds
  
  // 开发模式下显示调试信息
  if (import.meta.dev) {
    console.log('初始化用户角色选中状态:', {
      username: user.value.username,
      userRoleNames,
      availableRoles: availableRoles.value.map(r => ({ id: r.id, name: r.name, display_name: r.display_name })),
      selectedRoleIds: roleIds
    })
  }
}

// 监听数据变化，初始化选中状态
watch([user, availableRoles], () => {
  if (user.value && availableRoles.value.length > 0) {
    initializeSelectedRoles()
  }
}, { immediate: true })

// 为每个角色创建计算属性来支持 v-model
const getRoleModel = (roleId: number) => {
  return computed({
    get: () => selectedRoleIds.value.includes(roleId),
    set: (value: boolean) => {
      if (value) {
        if (!selectedRoleIds.value.includes(roleId)) {
          selectedRoleIds.value.push(roleId)
        }
      } else {
        const index = selectedRoleIds.value.indexOf(roleId)
        if (index > -1) {
          selectedRoleIds.value.splice(index, 1)
        }
      }
    }
  })
}

const selectAllInGroup = (groupType: string) => {
  const group = roleGroups.value.find(g => g.type === groupType)
  if (group) {
    group.roles.forEach(role => {
      if (!selectedRoleIds.value.includes(role.id)) {
        selectedRoleIds.value.push(role.id)
      }
    })
  }
}

const deselectAllInGroup = (groupType: string) => {
  const group = roleGroups.value.find(g => g.type === groupType)
  if (group) {
    group.roles.forEach(role => {
      const index = selectedRoleIds.value.indexOf(role.id)
      if (index > -1) {
        selectedRoleIds.value.splice(index, 1)
      }
    })
  }
}

const resetSelection = () => {
  initializeSelectedRoles()
}

// 事件处理
const handleSubmit = async () => {
  if (!user.value) return

  // 检查是否至少选择了一个角色
  if (!hasAtLeastOneRole.value) {
    const defaultRole = getDefaultRole()
    if (defaultRole) {
      // 自动添加默认角色（普通用户）
      selectedRoleIds.value.push(defaultRole.id)
      
      const toast = useToast()
      toast.add({
        title: "自动添加角色",
        description: `用户至少需要一个角色，已自动添加"${defaultRole.display_name}"角色`,
        color: "info",
      })
    } else {
      const toast = useToast()
      toast.add({
        title: "请选择角色",
        description: "用户至少需要选择一个角色",
        color: "warning",
      })
      return
    }
  }

  loading.value = true
  try {
    await rbacApi.assignUserRoles(user.value.id, selectedRoleIds.value)
    // 返回用户详情页
    navigateTo(`/users/${userId.value}`)
  } catch (error) {
    console.error("分配用户角色失败:", error)
    // 错误已由 useApi 自动处理
  } finally {
    loading.value = false
  }
}

const handleCancel = () => {
  navigateTo(`/users/${userId.value}`)
}

// 初始化数据
onMounted(async () => {
  // 数据已通过 useApiData 自动获取
})
</script> 
