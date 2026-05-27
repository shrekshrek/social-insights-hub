<template>
  <div>
    <div class="text-center mb-8">
      <h2 class="text-2xl font-bold text-gray-900">完成注册</h2>
      <p v-if="inviteToken" class="text-gray-600 mt-2">
        您通过邀请链接进入，请设置用户名和密码以完成注册
      </p>
    </div>

    <div v-if="!inviteToken" class="text-center py-8 space-y-4">
      <UIcon name="i-heroicons-exclamation-circle" class="h-10 w-10 text-amber-500" />
      <p class="text-gray-600 text-sm">
        本系统采用邀请制注册，请通过管理员发送的邀请邮件链接进入注册页面。
      </p>
      <p class="text-gray-500 text-xs">
        如已有账户，请直接
        <NuxtLink to="/login" class="text-blue-600 hover:text-blue-500 font-medium">
          登录
        </NuxtLink>
      </p>
    </div>

    <UForm
      v-else
      :schema="schema"
      :state="state"
      class="space-y-4"
      @submit="handleSubmit"
    >
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

        <UFormField label="密码" name="password">
          <UInput
            v-model="state.password"
            type="password"
            placeholder="请输入密码（至少 8 位，含字母和数字）"
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

    <div v-if="inviteToken" class="mt-8 text-center">
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
})

const route = useRoute();
const { register } = useAuthApi();
const { showError } = useApi();

const inviteToken = computed(() => {
  const t = route.query.token;
  return typeof t === 'string' && t.length > 0 ? t : null;
});

const loading = ref(false);

const state = reactive({
  username: '',
  password: '',
  passwordConfirm: '',
});

const schema = z.object({
  username: z
    .string()
    .min(3, '用户名至少需要 3 个字符')
    .max(50, '用户名最多 50 个字符')
    .regex(/^[a-zA-Z0-9_-]+$/, '用户名只能包含字母、数字、下划线和连字符'),
  password: z
    .string()
    .min(8, '密码至少需要 8 位')
    .regex(/[A-Za-z]/, '密码必须包含字母')
    .regex(/\d/, '密码必须包含数字'),
  passwordConfirm: z.string().min(8, '密码至少需要 8 位'),
}).refine(data => data.password === data.passwordConfirm, {
  message: '两次输入的密码不匹配',
  path: ['passwordConfirm'],
});

const handleSubmit = async (event: FormSubmitEvent<z.output<typeof schema>>) => {
  if (!inviteToken.value) return;

  loading.value = true;
  try {
    await register({
      username: event.data.username,
      password: event.data.password,
      invite_token: inviteToken.value,
    });
    await navigateTo('/dashboard');
  } catch (e) {
    console.error('Register error:', e);
    const err = e as {
      data?: {
        statusMessage?: string;
        message?: string;
        detail?: string;
        error?: { message?: string };
      };
      statusMessage?: string;
      message?: string;
      statusCode?: number;
      status?: number;
    };
    const status = err.statusCode ?? err.status;
    const backendMessage =
      err.data?.error?.message ||
      err.data?.statusMessage ||
      err.data?.message ||
      err.data?.detail ||
      err.statusMessage ||
      err.message;
    let message = backendMessage || '注册失败，请稍后重试';
    if (status === 400 && /邀请/.test(backendMessage || '')) {
      message = backendMessage as string;
    } else if (status === 409) {
      message = '用户名已被使用';
    }
    showError(message);
  } finally {
    loading.value = false;
  }
};
</script>
