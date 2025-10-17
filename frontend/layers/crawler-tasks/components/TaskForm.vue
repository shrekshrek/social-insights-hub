<template>
  <UForm
    :schema="schema"
    :state="formState"
    class="space-y-6"
    @submit="handleSubmit"
  >
    <!-- 基本信息 -->
    <div class="space-y-4">
      <UFormField label="任务名称" name="name" required>
        <UInput
          v-model="formState.name"
          placeholder="例如: 小红书-ChatGPT关键词采集"
          :disabled="loading"
        />
      </UFormField>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <UFormField label="平台" name="platform" required>
          <USelect
            v-model="formState.platform"
            :items="platformOptions"
            value-attribute="value"
            label-attribute="label"
            placeholder="请选择平台"
            :disabled="loading"
          />
        </UFormField>

        <UFormField label="爬取模式" name="crawler_type" required>
          <USelect
            v-model="formState.crawler_type"
            :items="crawlerTypeOptions"
            value-attribute="value"
            label-attribute="label"
            placeholder="请选择爬取模式"
            :disabled="loading"
          />
        </UFormField>
      </div>
    </div>

    <!-- 配置信息 -->
    <div class="space-y-4 pt-4 border-t border-gray-200 dark:border-gray-700">
      <h3 class="text-lg font-medium text-gray-900 dark:text-white">任务配置</h3>

      <!-- 关键词(搜索模式) -->
      <UFormField
        v-if="formState.crawler_type === 'search'"
        label="关键词"
        name="keywords"
        help="多个关键词用逗号分隔"
        required
      >
        <UInput
          v-model="formState.keywords"
          placeholder="例如: deepseek,chatgpt,AI"
          :disabled="loading"
          class="w-full"
        />
      </UFormField>

      <!-- URL列表(详情/创作者模式) -->
      <UFormField
        v-if="formState.crawler_type === 'detail' || formState.crawler_type === 'creator'"
        label="URL列表"
        name="urls"
        help="每行一个URL"
        required
      >
        <UTextarea
          v-model="urlsText"
          :rows="4"
          placeholder="https://example.com/post/123&#10;https://example.com/post/456"
          :disabled="loading"
          class="w-full"
        />
      </UFormField>

      <UFormField label="最大爬取数量" name="max_count" required>
        <UInput
          v-model.number="formState.max_count"
          type="number"
          :min="1"
          :max="1000"
          :disabled="loading"
        />
      </UFormField>

      <!-- 开关选项 -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <UFormField label="爬取评论" name="enable_comments">
          <USwitch v-model="formState.enable_comments" :disabled="loading" />
        </UFormField>

        <UFormField label="爬取二级评论" name="enable_sub_comments">
          <USwitch v-model="formState.enable_sub_comments" :disabled="loading" />
        </UFormField>

        <UFormField label="使用代理" name="proxy_enabled">
          <USwitch v-model="formState.proxy_enabled" :disabled="loading" />
        </UFormField>

        <UFormField label="启用断点续传" name="enable_checkpoint">
          <USwitch v-model="formState.enable_checkpoint" :disabled="loading" />
        </UFormField>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="flex justify-end gap-3 pt-6 border-t border-gray-200 dark:border-gray-700">
      <UButton
        variant="outline"
        :disabled="loading"
        @click="$emit('cancel')"
      >
        取消
      </UButton>

      <UButton
        type="submit"
        :loading="loading"
        color="primary"
      >
        创建任务
      </UButton>
    </div>
  </UForm>
</template>

<script setup lang="ts">
import { z } from 'zod'
import type { TaskCreateRequest, PlatformType, CrawlerType } from '../types'
import { usePlatformOptions, useCrawlerTypeOptions } from '../composables/usePlatformOptions'

// Props
interface Props {
  loading?: boolean
}

withDefaults(defineProps<Props>(), {
  loading: false
})

// Emits
const emit = defineEmits<{
  'submit': [data: TaskCreateRequest]
  'cancel': []
}>()

// 下拉选项
const platformOptions = usePlatformOptions()
const crawlerTypeOptions = useCrawlerTypeOptions()

// 表单状态
const formState = reactive({
  name: '',
  platform: undefined as string | undefined,
  crawler_type: undefined as string | undefined,
  keywords: '',
  max_count: 40,
  enable_comments: true,
  enable_sub_comments: false,
  proxy_enabled: true,
  enable_checkpoint: true
})

const urlsText = ref('')

// Zod 验证规则
const schema = computed(() => {
  const baseSchema = z.object({
    name: z.string().min(1, '请输入任务名称').max(255, '任务名称不能超过255个字符'),
    platform: z.string().optional(),
    crawler_type: z.string().optional(),
    max_count: z.number().min(1, '最小爬取数量为1').max(1000, '最大爬取数量为1000'),
    enable_comments: z.boolean(),
    enable_sub_comments: z.boolean(),
    proxy_enabled: z.boolean(),
    enable_checkpoint: z.boolean()
  })

  // 根据爬取模式添加条件验证
  if (formState.crawler_type === 'search') {
    return baseSchema.extend({
      keywords: z.string().min(1, '请输入关键词')
    })
  }

  if (formState.crawler_type === 'detail' || formState.crawler_type === 'creator') {
    return baseSchema.extend({
      keywords: z.string().optional()
    })
  }

  return baseSchema.extend({
    keywords: z.string().optional()
  })
})

// 提交处理
const handleSubmit = async () => {
  // 验证必填字段
  if (!formState.name || !formState.platform || !formState.crawler_type) {
    useToast().add({ title: '请填写完整信息', color: 'warning' })
    return
  }

  // 验证关键词（搜索模式）
  if (formState.crawler_type === 'search' && !formState.keywords) {
    useToast().add({ title: '请输入关键词', color: 'warning' })
    return
  }

  // 验证URL列表（详情/创作者模式）
  if ((formState.crawler_type === 'detail' || formState.crawler_type === 'creator') && !urlsText.value.trim()) {
    useToast().add({ title: '请输入URL列表', color: 'warning' })
    return
  }

  // 构建请求数据
  const config = {
    max_count: formState.max_count,
    enable_comments: formState.enable_comments,
    enable_sub_comments: formState.enable_sub_comments,
    proxy_enabled: formState.proxy_enabled,
    enable_checkpoint: formState.enable_checkpoint,
    ...(formState.crawler_type === 'search' && { keywords: formState.keywords }),
    ...(formState.crawler_type === 'detail' || formState.crawler_type === 'creator'
      ? { urls: urlsText.value.split('\n').filter(line => line.trim()) }
      : {})
  }

  const taskData: TaskCreateRequest = {
    name: formState.name,
    platform: formState.platform as PlatformType,
    crawler_type: formState.crawler_type as CrawlerType,
    config
  }

  emit('submit', taskData)
}

// 重置表单
const resetForm = () => {
  formState.name = ''
  formState.platform = undefined
  formState.crawler_type = undefined
  formState.keywords = ''
  formState.max_count = 40
  formState.enable_comments = true
  formState.enable_sub_comments = false
  formState.proxy_enabled = true
  formState.enable_checkpoint = true
  urlsText.value = ''
}

// 暴露方法
defineExpose({
  resetForm
})
</script>
