<template>
  <UModal
    :open="open"
    :title="isEdit ? '编辑账号' : '新增账号'"
    description="填写账号基础信息"
    :close="{ onClick: () => emit('update:open', false) }"
    :ui="{ footer: 'justify-end gap-3' }"
  >
    <template #body>
      <div class="space-y-5">
        <UForm :state="form" class="space-y-5">
          <UFormField label="平台" name="platform" required>
            <USelect
              v-model="form.platform"
              :items="platformOptions"
              value-attribute="value"
              label-attribute="label"
              :disabled="isEdit"
              placeholder="请选择平台"
              class="w-full"
            />
          </UFormField>

          <UFormField label="账号标识" name="account_name" required>
            <UInput v-model="form.account_name" placeholder="例如：xhs_account_01" class="w-full" />
          </UFormField>

          <UFormField label="Cookies" name="cookies" required>
            <UTextarea
              v-model="form.cookies"
              :rows="4"
              placeholder="粘贴账号登录 cookies"
              class="w-full"
            />
          </UFormField>

          <UFormField v-if="isEdit" label="启用状态" name="is_active">
            <USwitch v-model="form.is_active" />
          </UFormField>
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
import type { AccountResource, AccountCreatePayload, AccountUpdatePayload } from '../types'

interface Props {
  open?: boolean
  editing?: AccountResource | null
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  editing: null,
  loading: false,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  submit: [payload: AccountCreatePayload | AccountUpdatePayload, id?: number]
}>()

const platformOptions = [
  { label: '小红书', value: 'xhs' },
  { label: '微博', value: 'weibo' },
  { label: '抖音', value: 'douyin' },
  { label: '快手', value: 'kuaishou' },
  { label: '哔哩哔哩', value: 'bilibili' },
  { label: '贴吧', value: 'tieba' },
  { label: '知乎', value: 'zhihu' },
]

const form = reactive({
  platform: platformOptions[0]?.value ?? '',
  account_name: '',
  cookies: '',
  is_active: true,
})

const isEdit = computed(() => !!props.editing)

const resetForm = () => {
  form.platform = platformOptions[0]?.value ?? ''
  form.account_name = ''
  form.cookies = ''
  form.is_active = true
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      if (props.editing) {
        form.platform = props.editing.platform
        form.account_name = props.editing.account_name
        form.cookies = props.editing.cookies ?? ''
        form.is_active = props.editing.is_active
      } else {
        resetForm()
      }
    }
  },
  { immediate: true }
)

const handleSubmit = () => {
  if (!form.account_name || !form.cookies || (!isEdit.value && !form.platform)) {
    useToast().add({ title: '请填写完整信息', color: 'warning' })
    return
  }

  if (isEdit.value) {
    const payload: AccountUpdatePayload = {
      account_name: form.account_name,
      cookies: form.cookies,
      is_active: form.is_active,
    }
    emit('submit', payload, props.editing?.id)
  } else {
    const payload: AccountCreatePayload = {
      platform: form.platform,
      account_name: form.account_name,
      cookies: form.cookies,
    }
    emit('submit', payload)
  }
}
</script>
