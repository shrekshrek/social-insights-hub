<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col">
    <!-- 头部导航 - 全屏宽度背景 -->
    <header
      class="sticky top-0 z-50 bg-white/95 dark:bg-gray-900/95 backdrop-blur supports-[backdrop-filter]:bg-white/60 border-b border-gray-200 dark:border-gray-800"
    >
      <UContainer>
        <div class="flex h-16 items-center justify-between">
          <NuxtLink
            to="/"
            class="text-xl font-bold text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
          >
            全栈项目脚手架
          </NuxtLink>

          <!-- 桌面端导航 -->
          <div class="hidden lg:flex items-center gap-4">
            <!-- 颜色模式切换按钮 -->
            <ClientOnly>
              <UButton
                variant="ghost"
                size="sm"
                :icon="
                  $colorMode.value === 'dark'
                    ? 'i-heroicons-sun'
                    : 'i-heroicons-moon'
                "
                :aria-label="
                  $colorMode.value === 'dark'
                    ? '切换到浅色模式'
                    : '切换到深色模式'
                "
                @click="
                  $colorMode.preference =
                    $colorMode.value === 'dark' ? 'light' : 'dark'
                "
              />
              <template #fallback>
                <!-- SSR 时显示一个静态的月亮图标作为默认 -->
                <UButton
                  variant="ghost"
                  size="sm"
                  icon="i-heroicons-moon"
                  aria-label="主题切换"
                />
              </template>
            </ClientOnly>

            <template v-if="status === 'authenticated'">
              <ClientOnly>
                <NuxtLink
                  v-for="item in navigationLinks"
                  :key="item.path"
                  :to="item.path"
                  class="text-sm text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                >
                  {{ item.label }}
                </NuxtLink>
              </ClientOnly>

              <UDropdownMenu :items="userMenuItems" :content="{ align: 'end' }">
                <UAvatar
                  :text="data?.user?.username?.charAt(0)?.toUpperCase() || 'U'"
                  size="sm"
                  class="cursor-pointer"
                />

                <template #item="{ item }">
                  <UIcon
                    v-if="'icon' in item"
                    :name="(item as any).icon"
                    class="flex-shrink-0 h-4 w-4"
                  />
                  <span class="truncate">{{ item.label }}</span>
                </template>
              </UDropdownMenu>
            </template>

            <template v-else>
              <NuxtLink
                to="/login"
                class="text-sm text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                登录
              </NuxtLink>
              <UButton to="/register" size="sm"> 注册 </UButton>
            </template>
          </div>

          <!-- 移动端导航 -->
          <div class="flex lg:hidden items-center gap-3">
            <!-- 主题切换按钮 -->
            <ClientOnly>
              <UButton
                variant="ghost"
                size="sm"
                :icon="
                  $colorMode.value === 'dark'
                    ? 'i-heroicons-sun'
                    : 'i-heroicons-moon'
                "
                :aria-label="
                  $colorMode.value === 'dark'
                    ? '切换到浅色模式'
                    : '切换到深色模式'
                "
                @click="
                  $colorMode.preference =
                    $colorMode.value === 'dark' ? 'light' : 'dark'
                "
              />
              <template #fallback>
                <!-- SSR 时显示一个静态的月亮图标作为默认 -->
                <UButton
                  variant="ghost"
                  size="sm"
                  icon="i-heroicons-moon"
                  aria-label="主题切换"
                />
              </template>
            </ClientOnly>

            <!-- 用户头像（已认证时） -->
            <UAvatar
              v-if="status === 'authenticated'"
              :text="data?.user?.username?.charAt(0)?.toUpperCase() || 'U'"
              size="sm"
              class="cursor-pointer"
            />

            <!-- 汉堡菜单按钮 -->
            <UButton
              variant="ghost"
              size="sm"
              :icon="
                isMobileMenuOpen ? 'i-heroicons-x-mark' : 'i-heroicons-bars-3'
              "
              :aria-label="isMobileMenuOpen ? '关闭菜单' : '打开菜单'"
              @click="isMobileMenuOpen = !isMobileMenuOpen"
            />
          </div>
        </div>
      </UContainer>

      <!-- 移动端菜单面板 -->
      <div
        v-if="isMobileMenuOpen"
        class="lg:hidden bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800"
      >
        <UContainer>
          <div class="py-4 space-y-2">
            <template v-if="status === 'authenticated'">
              <ClientOnly>
                <NuxtLink
                  v-for="item in navigationLinks"
                  :key="item.path"
                  :to="item.path"
                  class="block px-3 py-2 text-base font-medium text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md transition-colors"
                  @click="isMobileMenuOpen = false"
                >
                  {{ item.label }}
                </NuxtLink>
              </ClientOnly>

              <!-- 分割线 -->
              <div
                class="border-t border-gray-200 dark:border-gray-700 my-2"
              />

              <!-- 用户菜单项 -->
              <div class="px-3 py-2">
                <p
                  class="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2"
                >
                  {{ data?.user?.username || "用户" }}
                </p>
                <div class="space-y-1">
                  <NuxtLink
                    to="/profile"
                    class="flex items-center gap-2 px-2 py-1.5 text-sm text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md transition-colors"
                    @click="isMobileMenuOpen = false"
                  >
                    <UIcon name="i-heroicons-user-circle" class="h-4 w-4" />
                    个人资料
                  </NuxtLink>
                  <NuxtLink
                    to="/settings"
                    class="flex items-center gap-2 px-2 py-1.5 text-sm text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md transition-colors"
                    @click="isMobileMenuOpen = false"
                  >
                    <UIcon name="i-heroicons-cog-6-tooth" class="h-4 w-4" />
                    账户设置
                  </NuxtLink>
                  <button
                    class="flex items-center gap-2 w-full px-2 py-1.5 text-sm text-gray-700 dark:text-gray-300 hover:text-red-600 dark:hover:text-red-400 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md transition-colors"
                    @click="handleSignOut"
                  >
                    <UIcon
                      name="i-heroicons-arrow-right-on-rectangle"
                      class="h-4 w-4"
                    />
                    登出
                  </button>
                </div>
              </div>
            </template>

            <template v-else>
              <NuxtLink
                to="/login"
                class="block px-3 py-2 text-base font-medium text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md transition-colors"
                @click="isMobileMenuOpen = false"
              >
                登录
              </NuxtLink>
              <NuxtLink
                to="/register"
                class="block px-3 py-2 text-base font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-md transition-colors"
                @click="isMobileMenuOpen = false"
              >
                注册
              </NuxtLink>
            </template>
          </div>
        </UContainer>
      </div>
    </header>

    <!-- 主内容区 - 自动扩展剩余空间 -->
    <main class="flex-1 py-8">
      <UContainer>
        <slot />
      </UContainer>
    </main>

    <!-- 页脚 - 全屏宽度背景，始终在底部 -->
    <footer
      class="border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900"
    >
      <UContainer>
        <div class="py-6 text-center">
          <p class="text-sm text-gray-600 dark:text-gray-400">
            © 2024 全栈项目脚手架. 保留所有权利。
          </p>
        </div>
      </UContainer>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import type { NavigationItem } from "~/config/routes";
import { getNavigationItems, getRoutePermissions } from "~/config/routes";

const { loggedIn, session } = useUserSession();
const { logout } = useAuthApi();
const permissions = usePermissions();

// 计算属性以兼容原有代码
const status = computed(() => loggedIn.value ? 'authenticated' : 'unauthenticated');
const data = computed(() => ({ user: session.value?.user }));

const hasRouteAccess = (path: string) => {
  // 统一从路由配置中读取权限要求，并复用现有权限检查能力
  const required = getRoutePermissions(path);
  if (!required) {
    return true;
  }

  const permissionsToCheck = Array.isArray(required) ? required : [required];
  return permissionsToCheck.every((permission) => permissions.hasPermission(permission));
};

// 导航基础数据从配置中生成，后续仅根据用户权限做过滤
const navigationLinks = computed<NavigationItem[]>(() => {
  if (status.value !== 'authenticated') {
    return [];
  }

  const baseNavigationItems = getNavigationItems();
  return baseNavigationItems.filter((item) => hasRouteAccess(item.path));
});

// 移动端菜单状态
const isMobileMenuOpen = ref(false);

// 监听路由变化，关闭移动端菜单
const route = useRoute();
watch(route, () => {
  isMobileMenuOpen.value = false;
});

// 仅在认证状态变化时加载权限，避免死循环
watch(status, (newStatus) => {
  if (
    newStatus === 'authenticated' &&
    !permissions.permissionsLoaded.value &&
    !permissions.permissionsLoading.value
  ) {
    // 登录后确保权限列表已加载，避免首次进入时菜单为空
    permissions.loadUserPermissions?.();
  }
}, { immediate: true });

// Nuxt UI v4 - 直接使用类型推断，items 为嵌套数组结构
const userMenuItems = computed(() => [
  [
    {
      label: data.value?.user?.username || "用户",
      slot: "account",
      disabled: true,
      type: "label" as const,
    },
  ],
  [
    {
      label: "个人资料",
      icon: "i-heroicons-user-circle",
      to: "/profile",
    },
    {
      label: "账户设置",
      icon: "i-heroicons-cog-6-tooth",
      to: "/settings",
    },
  ],
  [
    {
      label: "登出",
      icon: "i-heroicons-arrow-right-on-rectangle",
      onSelect: handleSignOut,
    },
  ],
]);

const handleSignOut = async () => {
  try {
    await logout();
  } catch (error) {
    console.error("Logout error:", error);
  } finally {
    isMobileMenuOpen.value = false;
  }
};
</script>
