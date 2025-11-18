<script setup lang="ts">
import type { DataTaskCreate } from '../../../types'
import { z } from 'zod'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const { createTask } = useTasks()
const { getProjects, getProject } = useSocialProjects()
const { getPlatforms } = usePlatforms()

// 从URL获取project_id（如果有的话）
const preselectedProjectId = route.query.project_id ? Number(route.query.project_id) : undefined

// 判断是否从项目详情页进入（有预选项目ID）
const isFromProjectDetail = computed(() => !!preselectedProjectId)

// 如果是从项目详情页进入，获取项目信息
const { data: preselectedProject } = preselectedProjectId
  ? getProject(preselectedProjectId)
  : { data: ref(null) }

// 获取平台列表
const { data: platforms } = getPlatforms()

// 表单状态
const submitting = ref(false)

// 计算返回路径
const cancelReturnPath = computed(() => {
  if (isFromProjectDetail.value && preselectedProjectId) {
    return `/social-insights/projects/${preselectedProjectId}`
  }
  return '/social-insights/tasks'
})

// 表单Schema
const schema = z.object({
  name: z.string().min(1, '任务名称不能为空').max(255, '任务名称不能超过255个字符'),
  description: z.string().optional(),
  project_id: z.number({ message: '请选择项目' }),
  platform_id: z.number({ message: '请选择平台' }),
  task_type: z.enum(['search', 'detail', 'creator', 'homefeed'], { message: '请选择任务类型' }),
  data_source: z.enum(['local_upload', 'remote_crawler'], { message: '请选择数据源' }),
  keywords: z.string().optional(),
  id_list: z.string().optional(),
})

// 表单初始值
const state = reactive<{
  name: string
  description: string
  project_id: number | undefined
  platform_id: number | undefined
  task_type: 'search' | 'detail' | 'creator' | 'homefeed'
  data_source: 'local_upload' | 'remote_crawler'
  keywords: string
  id_list: string
}>({
  name: '',
  description: '',
  project_id: preselectedProjectId,
  platform_id: undefined,
  task_type: 'search',
  data_source: 'local_upload',
  keywords: '',
  id_list: '',
})

// 项目搜索相关
const projectSearchQuery = ref('')
const projectSearchFocused = ref(false)
const searchingProjects = ref(false)
const selectedProjectCache = ref<{ id: number; name: string } | null>(null)

// 动态搜索参数
const projectSearchParams = computed(() => {
  const params: Record<string, unknown> = {
    page: 1,
    page_size: 50,
  }
  if (projectSearchQuery.value.trim()) {
    params.search = projectSearchQuery.value.trim()
  }
  return params
})

// 获取项目列表（根据搜索参数动态更新）
const { data: projectsData, pending: projectsPending } = getProjects(projectSearchParams)

// 项目选项
const projectOptions = computed(() => {
  if (!projectsData.value) return []
  return projectsData.value.items.map((p) => ({
    label: p.name,
    value: p.id,
  }))
})

// 选中的项目名称
const selectedProjectName = computed(() => {
  if (!state.project_id) return ''

  // 先从当前搜索结果中查找
  const fromResults = projectOptions.value.find(p => p.value === state.project_id)
  if (fromResults) return fromResults.label

  // 如果不在当前结果中，使用缓存的名称
  if (selectedProjectCache.value?.id === state.project_id) {
    return selectedProjectCache.value.name
  }

  return ''
})

// 防抖定时器
let searchDebounceTimer: NodeJS.Timeout | null = null

// 处理搜索输入（带防抖）
const handleSearchInput = (value: string) => {
  projectSearchQuery.value = value

  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }

  searchingProjects.value = true
  searchDebounceTimer = setTimeout(() => {
    searchingProjects.value = false
  }, 300)
}

// 选择项目
const selectProject = (projectId: number, projectName: string) => {
  state.project_id = projectId
  selectedProjectCache.value = { id: projectId, name: projectName }
  projectSearchQuery.value = ''
  projectSearchFocused.value = false
}

// 处理输入框焦点
const handleProjectInputFocus = () => {
  projectSearchFocused.value = true
  projectSearchQuery.value = ''
}

// 处理输入框失焦（延迟以允许点击选项）
const handleProjectInputBlur = () => {
  setTimeout(() => {
    projectSearchFocused.value = false
    projectSearchQuery.value = ''
  }, 200)
}

// 平台选项
const platformOptions = computed(() => {
  if (!platforms.value) return []
  return platforms.value.map((p) => ({
    label: p.name,
    value: p.id,
    description: p.description,
  }))
})

// 任务类型选项
const taskTypeOptions = [
  { label: '搜索任务', value: 'search', description: '通过关键词搜索帖子' },
  { label: '详情任务', value: 'detail', description: '获取特定帖子的详细信息' },
  { label: '作者任务', value: 'creator', description: '获取特定作者的帖子列表' },
  { label: '首页动态', value: 'homefeed', description: '获取首页推荐动态' },
]

// 数据源选项
const dataSourceOptions = [
  { label: '本地上传', value: 'local_upload', description: '上传本地JSON数据文件' },
  { label: '远程爬虫', value: 'remote_crawler', description: '通过WebSocket与爬虫平台通信（即将支持）' },
]

// 是否需要显示ID列表字段
const needsIdList = computed(() => {
  return state.task_type === 'detail' || state.task_type === 'creator'
})

// ID列表字段配置（根据平台和任务类型动态显示）
const idListConfig = computed(() => {
  if (!needsIdList.value) return null

  const platformCode = platforms.value?.find(p => p.id === state.platform_id)?.code
  const taskType = state.task_type

  // 如果还没选择平台，显示提示
  if (!platformCode) {
    return {
      label: taskType === 'detail' ? '内容ID/URL列表' : '创作者ID/URL列表',
      placeholder: '请先在下方选择目标平台',
      help: '选择平台后，此处会显示该平台所需的ID/URL格式说明',
    }
  }

  if (taskType === 'detail') {
    const configs: Record<string, { label: string; placeholder: string; help: string }> = {
      'xhs': {
        label: '笔记URL列表',
        placeholder: '请输入小红书笔记URL，每行一个\n例如：https://www.xiaohongshu.com/explore/xxx?xsec_token=xxx&xsec_source=pc_feed',
        help: '需要包含 xsec_token 和 xsec_source 参数',
      },
      'dy': {
        label: '视频ID列表',
        placeholder: '请输入抖音视频ID，每行一个\n例如：7566756334578830627',
        help: '从视频分享链接中获取数字ID',
      },
      'bili': {
        label: '视频BVID列表',
        placeholder: '请输入B站视频BVID，每行一个\n例如：BV1d54y1g7db',
        help: '从视频链接中获取BVID',
      },
      'ks': {
        label: '视频ID列表',
        placeholder: '请输入快手视频ID，每行一个\n例如：3xf8enb8dbj6uig',
        help: '从视频分享链接中获取ID',
      },
      'wb': {
        label: '微博ID列表',
        placeholder: '请输入微博ID，每行一个\n例如：5180657661643376',
        help: '从微博链接中获取数字ID',
      },
      'tieba': {
        label: '帖子ID列表',
        placeholder: '请输入贴吧帖子ID，每行一个\n例如：9815127841',
        help: '从帖子链接中获取ID',
      },
      'zhihu': {
        label: '内容URL列表',
        placeholder: '请输入知乎内容URL，每行一个\n支持回答、文章、视频、问题链接',
        help: '支持多种类型：回答、文章、视频、问题',
      },
    }
    return configs[platformCode] || null
  } else if (taskType === 'creator') {
    const configs: Record<string, { label: string; placeholder: string; help: string }> = {
      'xhs': {
        label: '创作者主页URL列表',
        placeholder: '请输入小红书创作者主页URL，每行一个\n例如：https://www.xiaohongshu.com/user/profile/xxx?xsec_token=xxx&xsec_source=pc_search',
        help: '需要包含 xsec_token 和 xsec_source 参数',
      },
      'dy': {
        label: '创作者Sec ID列表',
        placeholder: '请输入抖音创作者Sec ID，每行一个\n例如：MS4wLjABAAAATJPY7LAlaa5X-c8uNdWkvz0jUGgpw4eeXIwu_8BhvqE',
        help: '从创作者主页链接中获取Sec ID',
      },
      'bili': {
        label: 'UP主ID列表',
        placeholder: '请输入B站UP主ID，每行一个\n例如：434377496',
        help: '从UP主主页链接中获取数字ID',
      },
      'ks': {
        label: '创作者ID列表',
        placeholder: '请输入快手创作者ID，每行一个\n例如：3x4sm73aye7jq7i',
        help: '从创作者主页链接中获取ID',
      },
      'wb': {
        label: '创作者ID列表',
        placeholder: '请输入微博创作者ID，每行一个\n例如：2172061270',
        help: '从用户主页链接中获取数字ID',
      },
      'tieba': {
        label: '创作者主页URL列表',
        placeholder: '请输入贴吧创作者主页URL，每行一个\n例如：https://tieba.baidu.com/home/main/?id=tb.1.7f139e2e&fr=frs',
        help: '完整的用户主页链接',
      },
      'zhihu': {
        label: '创作者主页URL列表',
        placeholder: '请输入知乎创作者主页URL，每行一个\n例如：https://www.zhihu.com/people/yd1234567',
        help: '用户的个人主页链接',
      },
    }
    return configs[platformCode] || null
  }

  return null
})

// 提交表单
const handleSubmit = async () => {
  submitting.value = true
  try {
    const platformCode = platforms.value?.find(p => p.id === state.platform_id)?.code

    // 构建 task_params 对象
    const taskParams: Record<string, unknown> = {}

    // 处理 detail 和 creator 类型的 ID 列表
    if (state.id_list && state.id_list.trim()) {
      const idArray = state.id_list.trim().split('\n').filter(id => id.trim())

      if (state.task_type === 'detail') {
        const paramKey = {
          'xhs': 'XHS_SPECIFIED_NOTE_URL_LIST',
          'dy': 'DY_SPECIFIED_ID_LIST',
          'bili': 'BILI_SPECIFIED_ID_LIST',
          'ks': 'KS_SPECIFIED_ID_LIST',
          'wb': 'WEIBO_SPECIFIED_ID_LIST',
          'tieba': 'TIEBA_SPECIFIED_ID_LIST',
          'zhihu': 'ZHIHU_SPECIFIED_ID_LIST',
        }[platformCode || '']

        if (paramKey) {
          taskParams[paramKey] = idArray
        }
      } else if (state.task_type === 'creator') {
        const paramKey = {
          'xhs': 'XHS_CREATOR_URL_LIST',
          'dy': 'DY_CREATOR_ID_LIST',
          'bili': 'BILI_CREATOR_ID_LIST',
          'ks': 'KS_CREATOR_ID_LIST',
          'wb': 'WEIBO_CREATOR_ID_LIST',
          'tieba': 'TIEBA_CREATOR_URL_LIST',
          'zhihu': 'ZHIHU_CREATOR_URL_LIST',
        }[platformCode || '']

        if (paramKey) {
          taskParams[paramKey] = idArray
        }
      }
    }

    const taskData: DataTaskCreate = {
      name: state.name,
      description: state.description || undefined,
      project_id: state.project_id!,
      platform_id: state.platform_id!,
      task_type: state.task_type,
      data_source: state.data_source,
      keywords: state.keywords || undefined,
      task_params: Object.keys(taskParams).length > 0 ? taskParams : undefined,
    }

    const result = await createTask(taskData)

    // 如果是本地上传，直接跳转到上传页面
    if (result.data_source === 'local_upload') {
      await navigateTo(`/social-insights/tasks/${result.id}/upload`)
    } else {
      // 否则跳转到任务详情页
      await navigateTo(`/social-insights/tasks/${result.id}`)
    }
  } catch (error) {
    console.error('创建任务失败:', error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        新建任务
      </h1>
      <p class="text-gray-600 dark:text-gray-400 mt-1">
        创建一个新的数据采集任务
      </p>
    </div>

    <!-- 表单卡片 -->
    <UCard>
      <template #header>
        <h2 class="text-base font-semibold">
          任务信息
        </h2>
      </template>

      <UForm
        :schema="schema"
        :state="state"
        @submit="handleSubmit"
      >
        <div class="space-y-5">
          <!-- 任务名称和所属项目 - 两列并排 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <!-- 任务名称 -->
            <UFormField
              label="任务名称"
              name="name"
              required
            >
              <UInput
                v-model="state.name"
                placeholder="请输入任务名称"
                class="w-full"
              />
            </UFormField>

            <!-- 所属项目（从项目详情页进入时只显示项目名称） -->
            <UFormField
              v-if="isFromProjectDetail"
              label="所属项目"
            >
              <UInput
                :model-value="preselectedProject?.name || '加载中...'"
                disabled
                class="w-full"
              />
            </UFormField>

            <!-- 所属项目（从任务列表页进入时显示搜索选择器） -->
            <UFormField
              v-else
              label="所属项目"
              name="project_id"
              required
            >
              <div class="relative">
                <UInput
                  :model-value="projectSearchFocused ? projectSearchQuery : selectedProjectName"
                  placeholder="输入项目名称搜索..."
                  icon="i-lucide-search"
                  :loading="projectsPending"
                  class="w-full"
                  @update:model-value="handleSearchInput"
                  @focus="handleProjectInputFocus"
                  @blur="handleProjectInputBlur"
                />

                <!-- 下拉列表 -->
                <div
                  v-if="projectSearchFocused && !projectsPending"
                  class="absolute z-10 mt-1 w-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-60 overflow-auto"
                >
                  <!-- 有结果 -->
                  <template v-if="projectOptions.length > 0">
                    <button
                      v-for="project in projectOptions"
                      :key="project.value"
                      type="button"
                      class="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 text-sm"
                      :class="{
                        'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400': state.project_id === project.value
                      }"
                      @click="selectProject(project.value, project.label)"
                    >
                      {{ project.label }}
                    </button>
                  </template>

                  <!-- 无结果提示 -->
                  <div
                    v-else
                    class="px-3 py-2 text-sm text-gray-500"
                  >
                    {{ projectSearchQuery ? '未找到匹配的项目' : '开始输入以搜索项目' }}
                  </div>
                </div>

                <!-- 加载状态 -->
                <div
                  v-if="projectSearchFocused && projectsPending"
                  class="absolute z-10 mt-1 w-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg px-3 py-2"
                >
                  <div class="flex items-center gap-2 text-sm text-gray-500">
                    <UIcon name="i-lucide-loader-2" class="animate-spin" />
                    <span>搜索中...</span>
                  </div>
                </div>
              </div>
            </UFormField>
          </div>

          <!-- 任务描述 - 占据整行 -->
          <UFormField
            label="任务描述"
            name="description"
          >
            <UTextarea
              v-model="state.description"
              placeholder="请输入任务描述"
              :rows="3"
              class="w-full"
            />
          </UFormField>

          <!-- 任务类型和数据源 - 两列并排 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <!-- 任务类型 -->
            <UFormField
              label="任务类型"
              name="task_type"
              required
            >
              <USelect
                v-model="state.task_type"
                :items="taskTypeOptions"
                value-key="value"
                placeholder="选择任务类型"
                class="w-full"
              />
            </UFormField>

            <!-- 数据源 -->
            <UFormField
              label="数据源"
              name="data_source"
              required
            >
              <USelect
                v-model="state.data_source"
                :items="dataSourceOptions"
                value-key="value"
                placeholder="选择数据源"
                class="w-full"
                :disabled-items="['remote_crawler']"
              />
            </UFormField>
          </div>

          <!-- 关键词（仅search类型） -->
          <UFormField
            v-if="state.task_type === 'search'"
            label="搜索关键词"
            name="keywords"
            help="多个关键词请用逗号分隔"
          >
            <UInput
              v-model="state.keywords"
              placeholder="例如：热点话题,品牌名,产品名"
              class="w-full"
            />
          </UFormField>

          <!-- ID/URL列表（detail和creator类型） -->
          <UFormField
            v-if="idListConfig"
            :label="idListConfig.label"
            name="id_list"
            :help="idListConfig.help"
            required
          >
            <UTextarea
              v-model="state.id_list"
              :placeholder="idListConfig.placeholder"
              :rows="5"
              :disabled="!state.platform_id"
              class="w-full font-mono text-sm"
            />
          </UFormField>

          <!-- 目标平台 - 复选框网格 -->
          <UFormField
            label="目标平台"
            name="platform_id"
            required
          >
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              <label
                v-for="platform in platformOptions"
                :key="platform.value"
                class="relative flex items-start p-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-colors"
                :class="{
                  'ring-2 ring-primary-500 border-primary-500': state.platform_id === platform.value
                }"
              >
                <input
                  v-model="state.platform_id"
                  type="radio"
                  :value="platform.value"
                  class="mt-0.5 h-4 w-4 rounded-full border-gray-300 text-primary-600 focus:ring-primary-500"
                >
                <div class="ml-3 flex-1">
                  <div class="font-medium text-sm">
                    {{ platform.label }}
                  </div>
                  <div
                    v-if="platform.description"
                    class="text-xs text-gray-500 dark:text-gray-400 mt-0.5"
                  >
                    {{ platform.description }}
                  </div>
                </div>
              </label>
            </div>
          </UFormField>
        </div>
      </UForm>
    </UCard>

    <!-- 操作按钮 -->
    <div class="flex justify-end items-center gap-3">
      <UButton
        variant="outline"
        size="lg"
        @click="navigateTo(cancelReturnPath)"
      >
        取消
      </UButton>
      <UButton
        size="lg"
        :loading="submitting"
        @click="handleSubmit"
      >
        创建任务
      </UButton>
    </div>
  </div>
</template>
