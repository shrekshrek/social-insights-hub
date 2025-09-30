<template>
  <div>
    <div class="text-center mb-8">
      <h2 class="text-2xl font-bold text-gray-900">创建账户</h2>
      <p class="text-gray-600 mt-2">注册一个新账户</p>
    </div>

    <UForm :schema="schema" :state="state" class="space-y-4" @submit="handleSubmit">
      <div class="grid grid-cols-1 gap-4">
        <UFormField label="用户名" name="username">
          <UInput
            v-model="state.username"
            type="text"
            placeholder="请输入用户名"
            autocomplete="username"
            size="lg"
            required
          />
        </UFormField>

        <UFormField label="邮箱地址（可选）" name="email">
          <UInput
            v-model="state.email"
            type="email"
            placeholder="请输入邮箱地址（可选）"
            autocomplete="email"
            size="lg"
          />
        </UFormField>

        <UFormField label="密码" name="password">
          <UInput
            v-model="state.password"
            type="password"
            placeholder="请输入密码"
            autocomplete="new-password"
            size="lg"
            required
          />
        </UFormField>

        <UFormField label="确认密码" name="passwordConfirm">
          <UInput
            v-model="state.passwordConfirm"
            type="password"
            placeholder="请再次输入密码"
            autocomplete="new-password"
            size="lg"
            required
          />
        </UFormField>
      </div>

      <div v-if="errorMsg" class="text-sm text-red-600 text-center bg-red-50 p-3 rounded-md">
        {{ errorMsg }}
      </div>

      <UButton
        type="submit"
        block
        size="lg"
        :loading="loading"
        class="mt-6"
      >
        {{ loading ? '注册中...' : '注册' }}
      </UButton>
    </UForm>

    <div class="mt-8 text-center">
      <div class="text-sm text-gray-600">
        已有账户？
        <NuxtLink to="/login" class="text-blue-600 hover:text-blue-500 font-medium">
          立即登录
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { z } from 'zod';
import type { FormSubmitEvent } from '@nuxt/ui';

definePageMeta({
  layout: 'auth',
  // 认证保护已由全局认证守卫处理，无需重复定义
})

const { register } = useAuthApi();

const loading = ref(false);
const errorMsg = ref<string | null>(null);

const state = reactive({
  username: '',
  email: '' as string | undefined,
  password: '',
  passwordConfirm: '',
})

const schema = z.object({
  username: z.string().min(3, '用户名至少需要3个字符'),
  email: z.string().email('无效的邮箱地址').optional().or(z.literal('')),
  password: z.string().min(8, '密码至少需要8个字符'),
  passwordConfirm: z.string().min(8, '密码至少需要8个字符'),
}).refine(data => data.password === data.passwordConfirm, {
  message: "两次输入的密码不匹配",
  path: ["passwordConfirm"],
});

const handleSubmit = async (event: FormSubmitEvent<z.output<typeof schema>>) => {
  errorMsg.value = null;
  loading.value = true;
  try {
    await register({
      username: event.data.username,
      email: event.data.email || null, // 空字符串转为null
      password: event.data.password,
    });

    // 注册成功后已自动登录，直接跳转到工作台
    await navigateTo('/dashboard');

  } catch (e) {
    const error = e as { data?: { statusMessage?: string; detail?: string; error?: { message: string } } };
    errorMsg.value = error.data?.error?.message 
      || error.data?.statusMessage 
      || error.data?.detail 
      || '注册失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}
</script> 