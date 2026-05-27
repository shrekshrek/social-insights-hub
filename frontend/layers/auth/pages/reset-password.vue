<template>
  <div>
    <div class="text-center mb-8">
      <h2 class="text-2xl font-bold text-gray-900">重置密码</h2>
      <p v-if="resetToken" class="text-gray-600 mt-2">
        请设置新密码以完成重置
      </p>
    </div>

    <div v-if="!resetToken" class="text-center py-8 space-y-4">
      <UIcon name="i-heroicons-exclamation-circle" class="h-10 w-10 text-amber-500" />
      <p class="text-gray-600 text-sm">
        重置链接缺少 token，请通过管理员发送的重置邮件链接打开此页面。
      </p>
      <UButton to="/login" variant="outline" size="sm">返回登录</UButton>
    </div>

    <UForm
      v-else
      :schema="schema"
      :state="state"
      class="space-y-4"
      @submit="handleSubmit"
    >
      <UFormField label="新密码" name="password">
        <UInput
          v-model="state.password"
          type="password"
          placeholder="请输入新密码（至少 8 位，含字母和数字）"
          autocomplete="new-password"
          size="lg"
          required
        />
      </UFormField>

      <UFormField label="确认新密码" name="passwordConfirm">
        <UInput
          v-model="state.passwordConfirm"
          type="password"
          placeholder="请再次输入新密码"
          autocomplete="new-password"
          size="lg"
          required
        />
      </UFormField>

      <UButton
        type="submit"
        block
        size="lg"
        :loading="loading"
        class="mt-6"
      >
        {{ loading ? '提交中...' : '重置密码' }}
      </UButton>
    </UForm>
  </div>
</template>

<script setup lang="ts">
import { z } from 'zod';
import type { FormSubmitEvent } from '@nuxt/ui';

definePageMeta({
  layout: 'auth',
});

const route = useRoute();
const { resetPasswordWithToken } = useAuthApi();
const { showError } = useApi();

const resetToken = computed(() => {
  const t = route.query.token;
  return typeof t === 'string' && t.length > 0 ? t : null;
});

const loading = ref(false);

const state = reactive({
  password: '',
  passwordConfirm: '',
});

const schema = z.object({
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
  if (!resetToken.value) return;

  loading.value = true;
  try {
    await resetPasswordWithToken({
      token: resetToken.value,
      new_password: event.data.password,
    });
    await navigateTo('/login', { replace: true });
  } catch (e) {
    console.error('Reset password error:', e);
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
    const message =
      status === 400
        ? backendMessage || '重置链接无效或已过期'
        : backendMessage || '重置失败，请稍后重试';
    showError(message);
  } finally {
    loading.value = false;
  }
};
</script>
