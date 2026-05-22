<template>
  <div>
    <div class="text-center mb-8">
      <h2 class="text-2xl font-bold text-gray-900">登录</h2>
      <p class="text-gray-600 mt-2">使用飞书账号登录系统</p>
    </div>

    <UButton
      block
      size="xl"
      :loading="isFeishuLoading"
      @click="handleFeishuLogin"
    >
      <template #leading>
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M3 7.5L10.5 3L21 13.5L13.5 18L3 7.5Z" fill="#00D6B9" />
          <path d="M3 7.5L13.5 18L10.5 21L3 7.5Z" fill="#133C9A" />
          <path d="M10.5 3L21 13.5L13.5 18L10.5 3Z" fill="#3370FF" />
        </svg>
      </template>
      {{ isFeishuLoading ? "跳转中..." : "飞书扫码登录" }}
    </UButton>

    <div class="mt-8">
      <button
        type="button"
        class="w-full text-center text-sm text-gray-400 hover:text-gray-600 transition-colors"
        @click="showPasswordLogin = !showPasswordLogin"
      >
        {{ showPasswordLogin ? "收起" : "使用账号密码登录" }}
      </button>

      <Transition
        enter-active-class="transition-all duration-200 ease-out"
        enter-from-class="opacity-0 max-h-0"
        enter-to-class="opacity-100 max-h-80"
        leave-active-class="transition-all duration-150 ease-in"
        leave-from-class="opacity-100 max-h-80"
        leave-to-class="opacity-0 max-h-0"
      >
        <div v-if="showPasswordLogin" class="overflow-hidden mt-4">
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

            <UButton type="submit" block size="lg" variant="outline" :loading="isLoading">
              {{ isLoading ? "登录中..." : "登录" }}
            </UButton>
          </UForm>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { z } from "zod";
import type { FormSubmitEvent } from "@nuxt/ui";

definePageMeta({
  layout: "auth",
});

const { login, feishuLogin } = useAuthApi();
const { showError } = useApi();
const isLoading = ref(false);
const isFeishuLoading = ref(false);
const showPasswordLogin = ref(false);

const schema = z.object({
  username: z.string().min(1, "用户名不能为空"),
  password: z.string().min(6, "密码至少需要6位"),
});

type Schema = z.output<typeof schema>;

const state = reactive<Schema>({
  username: "",
  password: "",
});

async function handleFeishuLogin() {
  isFeishuLoading.value = true;
  try {
    await feishuLogin();
  } catch (error) {
    console.error("Feishu login error:", error);
    showError("飞书登录跳转失败，请稍后重试");
    isFeishuLoading.value = false;
  }
}

async function handleLogin(event: FormSubmitEvent<Schema>) {
  isLoading.value = true;
  try {
    await login({
      username: event.data.username,
      password: event.data.password,
    });
    await navigateTo("/dashboard", { replace: true });
  } catch (error) {
    console.error("Login error:", error);
    const err = error as {
      data?: { statusMessage?: string; message?: string; detail?: string };
      statusMessage?: string;
      message?: string;
      statusCode?: number;
      status?: number;
    };
    const status = err.statusCode ?? err.status;
    const backendMessage =
      err.data?.statusMessage ||
      err.data?.message ||
      err.data?.detail ||
      err.statusMessage ||
      err.message;
    const message =
      status === 401
        ? "用户名或密码错误"
        : backendMessage || "登录失败，请稍后重试";
    showError(message);
  } finally {
    isLoading.value = false;
  }
}
</script>
