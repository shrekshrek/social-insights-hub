<template>
  <UModal
    :open="open"
    :title="isEdit ? '编辑代理服务商' : '新增代理服务商'"
    description="配置快代理凭证与池参数，系统将按需自动拉取 IP。"
    :close="{ onClick: () => emit('update:open', false) }"
    :ui="{ footer: 'justify-end gap-3' }"
  >
    <template #body>
      <div class="space-y-6">
        <UAlert
          v-if="!isEdit"
          color="primary"
          variant="soft"
          title="提示"
          description="目前仅支持快代理（KuaiDaiLi），请在快代理控制台获取密钥并填写以下信息。"
        />
        <UForm :state="form" class="space-y-4">
          <UFormField label="配置名称" name="name" required>
            <UInput v-model="form.name" placeholder="例如：默认快代理" class="w-full" />
          </UFormField>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <UFormField label="Secret ID" name="secret_id" required>
              <UInput v-model="form.secret_id" placeholder="快代理 secret_id" class="w-full" />
            </UFormField>
            <UFormField label="Signature" name="signature" required>
              <UInput v-model="form.signature" placeholder="快代理 signature" class="w-full" />
            </UFormField>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <UFormField label="用户名" name="username" required>
              <UInput v-model="form.username" placeholder="快代理账号用户名" class="w-full" />
            </UFormField>
            <UFormField label="密码" name="password" required>
              <UInput v-model="form.password" type="password" placeholder="快代理账号密码" class="w-full" />
            </UFormField>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <UFormField label="池容量" name="pool_size">
              <UInput v-model.number="form.pool_size" type="number" min="1" max="200" class="w-full" />
            </UFormField>
            <UFormField label="同步间隔（分钟）" name="sync_interval_minutes">
              <UInput v-model.number="form.sync_interval_minutes" type="number" min="1" max="120" class="w-full" />
            </UFormField>
          </div>

          <div class="flex flex-wrap items-center gap-4">
            <UCheckbox v-model="form.validate_enabled" label="启用可用性校验" />
            <UCheckbox v-model="form.is_active" label="启用该服务商" />
          </div>
        </UForm>
      </div>
    </template>

    <template #footer>
      <UButton variant="outline" @click="emit('update:open', false)">取消</UButton>
      <UButton :loading="loading" color="primary" @click="handleSubmit">
        {{ isEdit ? '保存' : '创建' }}
      </UButton>
    </template>
  </UModal>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type {
  ProxyProvider,
  ProxyProviderCreatePayload,
  ProxyProviderUpdatePayload,
} from '../types'

interface Props {
  open?: boolean
  editing?: ProxyProvider | null
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  editing: null,
  loading: false,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  submit: [payload: ProxyProviderCreatePayload | ProxyProviderUpdatePayload, id?: number]
}>()

const form = reactive({
  name: '',
  secret_id: '',
  signature: '',
  username: '',
  password: '',
  pool_size: 10,
  sync_interval_minutes: 5,
  validate_enabled: true,
  is_active: true,
})

const isEdit = computed(() => !!props.editing)

const resetForm = () => {
  form.name = ''
  form.secret_id = ''
  form.signature = ''
  form.username = ''
  form.password = ''
  form.pool_size = 10
  form.sync_interval_minutes = 5
  form.validate_enabled = true
  form.is_active = true
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    if (props.editing) {
      form.name = props.editing.name
      form.secret_id = props.editing.secret_id
      form.signature = props.editing.signature
      form.username = props.editing.username
      form.password = props.editing.password
      form.pool_size = props.editing.pool_size
      form.sync_interval_minutes = props.editing.sync_interval_minutes
      form.validate_enabled = props.editing.validate_enabled
      form.is_active = props.editing.is_active
    } else {
      resetForm()
    }
  },
  { immediate: true },
)

const handleSubmit = () => {
  if (!form.name || !form.secret_id || !form.signature || !form.username || !form.password) {
    useToast().add({ title: '请填写完整的快代理凭证信息', color: 'warning' })
    return
  }

  if (isEdit.value) {
    const payload: ProxyProviderUpdatePayload = {
      name: form.name,
      secret_id: form.secret_id,
      signature: form.signature,
      username: form.username,
      password: form.password,
      pool_size: form.pool_size,
      sync_interval_minutes: form.sync_interval_minutes,
      validate_enabled: form.validate_enabled,
      is_active: form.is_active,
    }
    emit('submit', payload, props.editing?.id)
  } else {
    const payload: ProxyProviderCreatePayload = {
      name: form.name,
      secret_id: form.secret_id,
      signature: form.signature,
      username: form.username,
      password: form.password,
      pool_size: form.pool_size,
      sync_interval_minutes: form.sync_interval_minutes,
      validate_enabled: form.validate_enabled,
      is_active: form.is_active,
    }
    emit('submit', payload)
  }
}
</script>
