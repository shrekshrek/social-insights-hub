<template>
  <div>
    <div class="text-center mb-8">
      <h2 class="text-2xl font-bold text-gray-900">登录</h2>
      <p class="text-gray-600 mt-2">请登录您的账户</p>
    </div>

    <UForm
      :schema="schema"
      :state="state"
      class="space-y-4"
      @submit="handleLogin"
    >
      <UFormField label="用户名" name="username">
        <UInput
          v-model="state.username"
          type="text"
          placeholder="请输入用户名"
          size="lg"
          required
        />
      </UFormField>

      <UFormField label="密码" name="password">
        <UInput
          v-model="state.password"
          type="password"
          placeholder="请输入密码"
          size="lg"
          required
        />
      </UFormField>

      <UButton type="submit" block size="lg" :loading="isLoading" class="mt-6">
        {{ isLoading ? "登录中..." : "登录" }}
      </UButton>
    </UForm>

    <div class="mt-8 text-center space-y-4">
      <div class="text-sm text-gray-600">
        还没有账户？
        <NuxtLink
          to="/register"
          class="text-blue-600 hover:text-blue-500 font-medium"
        >
          立即注册
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { z } from "zod";
import type { FormSubmitEvent } from "@nuxt/ui";

definePageMeta({
  layout: "auth",
  // 认证保护已由全局认证守卫处理，无需重复定义
});

const { login } = useAuthApi();
const isLoading = ref(false);

const schema = z.object({
  username: z.string().min(1, "用户名不能为空"),
  password: z.string().min(6, "密码至少需要6位"),
});

type Schema = z.output<typeof schema>;

const state = reactive<Schema>({
  username: "",
  password: "",
});

async function handleLogin(event: FormSubmitEvent<Schema>) {
  isLoading.value = true;
  try {
    // 使用新的login方法
    await login({
      username: event.data.username,
      password: event.data.password,
    });
    
    // 登录成功后跳转到工作台
    await navigateTo("/dashboard");
  } catch (error) {
    // 错误已经由 useAuthApi 处理并显示toast
    console.error("Login error:", error);
  } finally {
    isLoading.value = false;
  }
}
</script>
