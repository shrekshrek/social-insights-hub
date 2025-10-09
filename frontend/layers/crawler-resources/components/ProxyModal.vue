<template>
  <UModal
    :open="open"
    :title="isEdit ? '编辑代理' : '新增代理'"
    :close="{ onClick: () => emit('update:open', false) }"
    :ui="{ footer: 'justify-end gap-3' }"
  >
    <template #body>
      <div class="space-y-4">
        <UForm :state="form" class="space-y-4">
          <UFormGroup label="标签">
            <UInput v-model="form.label" placeholder="例如：默认代理池" />
          </UFormGroup>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <UFormGroup label="协议" required>
              <USelect v-model="form.protocol" :options="protocolOptions" />
            </UFormGroup>
            <UFormGroup label="端口" required>
              <UInput v-model.number="form.port" type="number" min="1" max="65535" />
            </UFormGroup>
          </div>

          <UFormGroup label="主机地址" required>
            <UInput v-model="form.host" placeholder="例如：127.0.0.1" />
          </UFormGroup>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <UFormGroup label="用户名">
              <UInput v-model="form.username" />
            </UFormGroup>
            <UFormGroup label="密码">
              <UInput v-model="form.password" type="password" />
            </UFormGroup>
          </div>

          <UFormGroup v-if="isEdit" label="启用状态">
            <USwitch v-model="form.is_active" />
          </UFormGroup>
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
import type { ProxyResource, ProxyCreatePayload, ProxyUpdatePayload } from '../types'

interface Props {
  open?: boolean
  editing?: ProxyResource | null
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  editing: null,
  loading: false,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  submit: [payload: ProxyCreatePayload | ProxyUpdatePayload, id?: number]
}>()

const form = reactive({
  label: '',
  protocol: 'http',
  host: '',
  port: 8080,
  username: '',
  password: '',
  is_active: true,
})

const protocolOptions = [
  { label: 'HTTP', value: 'http' },
  { label: 'HTTPS', value: 'https' },
  { label: 'SOCKS5', value: 'socks5' },
]

const isEdit = computed(() => !!props.editing)

const resetForm = () => {
  form.label = ''
  form.protocol = 'http'
  form.host = ''
  form.port = 8080
  form.username = ''
  form.password = ''
  form.is_active = true
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      if (props.editing) {
        form.label = props.editing.label ?? ''
        form.protocol = props.editing.protocol
        form.host = props.editing.host
        form.port = props.editing.port
        form.username = props.editing.username ?? ''
        form.password = props.editing.password ?? ''
        form.is_active = props.editing.is_active
      } else {
        resetForm()
      }
    }
  },
  { immediate: true }
)

const handleSubmit = () => {
  if (!form.host || !form.port) {
    useToast().add({ title: '请填写完整信息', color: 'warning' })
    return
  }

  if (isEdit.value) {
    const payload: ProxyUpdatePayload = {
      label: form.label || null,
      protocol: form.protocol,
      host: form.host,
      port: form.port,
      username: form.username || null,
      password: form.password || null,
      is_active: form.is_active,
    }
    emit('submit', payload, props.editing?.id)
  } else {
    const payload: ProxyCreatePayload = {
      label: form.label || undefined,
      protocol: form.protocol,
      host: form.host,
      port: form.port,
      username: form.username || undefined,
      password: form.password || undefined,
    }
    emit('submit', payload)
  }
}
</script>
