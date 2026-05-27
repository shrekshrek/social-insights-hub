<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <div class="flex items-center gap-3">
      <UButton
        variant="ghost"
        icon="i-heroicons-arrow-left"
        @click="handleBack"
      />
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">邀请用户</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          通过邮件邀请新用户注册（受邀者凭邮件链接设置用户名和密码）
        </p>
      </div>
    </div>

    <UCard>
      <UForm
        :schema="schema"
        :state="state"
        class="space-y-6"
        @submit="handleSubmit"
      >
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <UFormField label="被邀请人邮箱" name="email" required>
            <UInput
              v-model="state.email"
              type="email"
              placeholder="example@company.com"
              autocomplete="off"
              size="lg"
            />
          </UFormField>

          <UFormField
            label="默认角色（可选）"
            name="default_role_id"
            help="留空则使用系统默认角色"
          >
            <USelectMenu
              v-model="state.default_role_id"
              :items="roleOptions"
              value-key="value"
              label-key="label"
              placeholder="选择默认角色"
              size="lg"
              class="w-full"
            />
          </UFormField>
        </div>

        <div class="flex items-center gap-3 pt-2">
          <UButton type="submit" :loading="submitting" size="lg">
            {{ submitting ? '发送中...' : '发送邀请邮件' }}
          </UButton>
          <UButton
            type="button"
            variant="outline"
            :disabled="submitting"
            @click="handleBack"
          >
            取消
          </UButton>
        </div>
      </UForm>
    </UCard>
  </div>
</template>

<script setup lang="ts">
import { z } from 'zod';
import type { FormSubmitEvent } from '@nuxt/ui';
import type { Role } from '../../types';

definePageMeta({
  title: '邀请用户',
  description: '通过邮件邀请新用户注册',
});

const { sendInvitation } = useUsersApi();
const rbacApi = useRbacApi();

const submitting = ref(false);

const state = reactive<{ email: string; default_role_id: number | null }>({
  email: '',
  default_role_id: null,
});

const schema = z.object({
  email: z.string().email('请输入有效的邮箱地址'),
  default_role_id: z.number().nullable().optional(),
});

const { data: rolesData } = rbacApi.getRoles();
const roleOptions = computed(() => {
  const items = (rolesData.value?.items ?? []) as Role[];
  return [
    { value: null, label: '系统默认' },
    ...items.map((r) => ({ value: r.id, label: r.display_name || r.name })),
  ];
});

const handleBack = () => {
  navigateTo('/users');
};

const handleSubmit = async (event: FormSubmitEvent<z.output<typeof schema>>) => {
  submitting.value = true;
  try {
    await sendInvitation({
      email: event.data.email,
      default_role_id: event.data.default_role_id ?? null,
    });
    await navigateTo('/users');
  } catch {
    // 错误已由 useApi 的 onResponseError 自动 toast
  } finally {
    submitting.value = false;
  }
};
</script>
