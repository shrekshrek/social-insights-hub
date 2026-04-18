<template>
  <div>
    <div class="text-center mb-8">
      <h2 class="text-2xl font-bold text-gray-900">飞书登录</h2>
    </div>

    <div class="flex flex-col items-center py-8 space-y-4">
      <template v-if="error">
        <UIcon name="i-heroicons-exclamation-circle" class="h-10 w-10 text-red-500" />
        <p class="text-gray-600 text-sm text-center">{{ error }}</p>
        <UButton to="/login" variant="outline" size="sm">返回登录</UButton>
      </template>
      <template v-else>
        <UIcon name="i-heroicons-arrow-path" class="h-10 w-10 text-primary animate-spin" />
        <p class="text-gray-500 text-sm">正在完成登录...</p>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({
  layout: 'auth',
});

const route = useRoute();
const error = ref<string | null>(null);
const { feishuCallback } = useAuthApi();

onMounted(async () => {
  const code = route.query.code as string | undefined;
  const state = route.query.state as string | undefined;

  if (!code || !state) {
    error.value = '缺少授权参数，请重新扫码登录';
    return;
  }

  try {
    await feishuCallback(code, state);
    await navigateTo('/dashboard', { replace: true });
  } catch (err: unknown) {
    const errData = err as { data?: { message?: string }; message?: string };
    error.value = errData?.data?.message || errData?.message || '飞书登录失败，请稍后重试';
  }
});
</script>
