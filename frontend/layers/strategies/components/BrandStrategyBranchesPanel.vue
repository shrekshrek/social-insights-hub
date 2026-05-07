<template>
  <UCard>
    <template #header>
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <div class="flex items-center gap-2 flex-wrap">
          <UBadge color="warning" variant="subtle" size="sm">第 2/3 层（多分支）</UBadge>
          <h3 class="text-lg font-semibold">Brand Role + Big Idea</h3>
          <span class="text-sm text-gray-500">{{ branchCountText }}</span>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <UButton
            v-if="branches.length > 1 && canEdit"
            size="xs"
            variant="ghost"
            :disabled="anyLoading"
            @click="allChecked ? uncheckAll() : checkAll()"
          >
            {{ allChecked ? '全不选' : '全选' }}
          </UButton>
          <UButton
            v-if="canGenerateBrandRole"
            size="sm"
            :loading="generatingBrandRoleAll"
            :disabled="anyLoading || pendingBrandRoleIds.length === 0"
            icon="i-heroicons-sparkles"
            @click="handleGenerateBrandRole"
          >
            生成 Brand Role
            <span v-if="pendingBrandRoleIds.length > 0" class="ml-1 text-xs opacity-80">
              ({{ pendingBrandRoleIds.length }})
            </span>
          </UButton>
          <UButton
            v-if="canGenerateBigIdea"
            size="sm"
            color="primary"
            :loading="generatingBigIdeaAll"
            :disabled="anyLoading || pendingBigIdeaIds.length === 0"
            icon="i-heroicons-light-bulb"
            @click="handleGenerateBigIdea"
          >
            生成 Big Idea
            <span v-if="pendingBigIdeaIds.length > 0" class="ml-1 text-xs opacity-80">
              ({{ pendingBigIdeaIds.length }})
            </span>
          </UButton>
        </div>
      </div>
    </template>

    <div v-if="!branches.length" class="text-center py-8 text-gray-400">
      {{ insightReady ? '请先完成第 1 层 Insight 洞察以初始化分支' : '请先完成第 1 层 Insight 洞察' }}
    </div>

    <template v-else>
      <p v-if="canEdit" class="text-xs text-gray-500 mb-3">
        勾选要生成 / 重生成的分支后点击右上按钮。默认全选 = 全跑模式（重置所有分支）；
        取消部分勾选 = 子集模式（仅跑勾选项，其他分支保留）。
      </p>

      <div class="space-y-4">
      <div
        v-for="branch in branches"
        :key="branch.tension_id"
        class="rounded-lg border p-4"
        :class="branch.selected
          ? 'border-primary-500 bg-primary-50/50 dark:bg-primary-950/20'
          : 'border-gray-200 dark:border-gray-700'"
      >
        <!-- 分支头部 -->
        <div class="flex items-start justify-between gap-2 flex-wrap mb-3">
          <div class="flex-1 min-w-0 flex gap-3 items-start">
            <UCheckbox
              v-if="canEdit"
              :model-value="isBranchChecked(branch.tension_id)"
              :disabled="anyLoading"
              class="mt-0.5"
              @update:model-value="toggleBranchChecked(branch.tension_id)"
            />
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <UBadge :color="statusColor(branch.status)" variant="subtle" size="xs">
                  {{ statusLabel(branch.status) }}
                </UBadge>
                <span class="font-semibold">分支 #{{ branch.tension_id + 1 }}</span>
                <UBadge v-if="branch.selected" color="primary" size="xs">
                  <UIcon name="i-heroicons-star-solid" class="w-3 h-3 mr-0.5" />
                  主推
                </UBadge>
              </div>
              <p class="text-sm text-gray-600 dark:text-gray-300 mt-1">
                {{ branch.tension_summary || `Tension ${branch.tension_id + 1}` }}
              </p>
              <p v-if="branch.error_message" class="text-xs text-error-600 mt-1">
                ✗ {{ branch.error_message }}
              </p>
            </div>
          </div>
          <div class="flex items-center gap-1 flex-wrap">
            <UButton
              v-if="!branch.selected && canEdit"
              size="xs"
              variant="outline"
              icon="i-heroicons-star"
              :disabled="anyLoading"
              @click="emit('select-branch', branch.tension_id)"
            >
              设为主推
            </UButton>
            <UButton
              v-if="canEdit"
              size="xs"
              variant="ghost"
              icon="i-heroicons-arrow-path"
              :loading="regeneratingBrandRoleId === branch.tension_id"
              :disabled="anyLoading"
              @click="confirmAndEmitBranch('regenerate-brand-role', branch.tension_id, `重新生成分支 #${branch.tension_id + 1} 的 Brand Role 会清空该分支 Big Idea，确定继续？`)"
            >
              重生成 Brand Role
            </UButton>
            <UButton
              v-if="branch.brand_role && canEdit"
              size="xs"
              variant="ghost"
              icon="i-heroicons-light-bulb"
              :loading="regeneratingBigIdeaId === branch.tension_id"
              :disabled="anyLoading"
              @click="confirmAndEmitBranch('regenerate-big-idea', branch.tension_id, `重新生成分支 #${branch.tension_id + 1} 的 Big Idea，确定继续？`)"
            >
              重生成 Big Idea
            </UButton>
          </div>
        </div>

        <!-- Brand Role 区 -->
        <div class="border-t border-gray-100 dark:border-gray-800 pt-3 mt-2">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-200 flex items-center gap-2 flex-wrap">
              <UBadge color="warning" variant="subtle" size="xs">第 2 层</UBadge>
              Brand Role 品牌角色
              <DataProvenanceBadge
                v-if="branchProvenance(branch, 'brand_role')"
                :provenance="branchProvenance(branch, 'brand_role')"
                :chain-inputs="branchChainInputs(branch, 'brand_role')"
                :modal-title="`分支 #${branch.tension_id + 1} · Brand Role · 原始数据来源`"
              />
            </span>
            <UButton
              v-if="branch.brand_role && canEdit"
              size="xs"
              variant="ghost"
              icon="i-heroicons-pencil-square"
              :disabled="anyLoading"
              @click="toggleEdit('brand_role', branch.tension_id)"
            >
              {{ isEditing('brand_role', branch.tension_id) ? '取消' : '编辑' }}
            </UButton>
            <UButton
              v-if="isEditing('brand_role', branch.tension_id)"
              size="xs"
              color="primary"
              icon="i-heroicons-check"
              :loading="savingBrandRoleId === branch.tension_id"
              @click="handleSaveBrandRole(branch.tension_id)"
            >
              保存
            </UButton>
          </div>
          <div v-if="!branch.brand_role" class="text-sm text-gray-400 py-2">未生成</div>
          <div v-else-if="isEditing('brand_role', branch.tension_id)">
            <BrandRoleEditForm
              :ref="(el: unknown) => setEditRef('brand_role', branch.tension_id, el)"
              :result="(branch.brand_role as unknown) as BrandRoleResult"
            />
          </div>
          <BrandRoleContent v-else :result="(branch.brand_role as unknown) as BrandRoleResult" />
        </div>

        <!-- Big Idea 区 -->
        <div class="border-t border-gray-100 dark:border-gray-800 pt-3 mt-3">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-200 flex items-center gap-2 flex-wrap">
              <UBadge color="success" variant="subtle" size="xs">第 3 层</UBadge>
              Big Idea 创意
              <DataProvenanceBadge
                v-if="branchProvenance(branch, 'big_idea')"
                :provenance="branchProvenance(branch, 'big_idea')"
                :chain-inputs="branchChainInputs(branch, 'big_idea')"
                :modal-title="`分支 #${branch.tension_id + 1} · Big Idea · 原始数据来源`"
              />
            </span>
            <UButton
              v-if="branch.big_idea && canEdit"
              size="xs"
              variant="ghost"
              icon="i-heroicons-pencil-square"
              :disabled="anyLoading"
              @click="toggleEdit('big_idea', branch.tension_id)"
            >
              {{ isEditing('big_idea', branch.tension_id) ? '取消' : '编辑' }}
            </UButton>
            <UButton
              v-if="isEditing('big_idea', branch.tension_id)"
              size="xs"
              color="primary"
              icon="i-heroicons-check"
              :loading="savingBigIdeaId === branch.tension_id"
              @click="handleSaveBigIdea(branch.tension_id)"
            >
              保存
            </UButton>
          </div>
          <div v-if="!branch.big_idea" class="text-sm text-gray-400 py-2">
            {{ branch.brand_role ? '点击右上「重生成 Big Idea」开始' : '需先完成 Brand Role' }}
          </div>
          <div v-else-if="isEditing('big_idea', branch.tension_id)">
            <BigIdeaEditForm
              :ref="(el: unknown) => setEditRef('big_idea', branch.tension_id, el)"
              :result="(branch.big_idea as unknown) as BigIdeaResult"
            />
          </div>
          <BigIdeaContent v-else :result="(branch.big_idea as unknown) as BigIdeaResult" />
        </div>
      </div>
    </div>
    </template>
  </UCard>
</template>

<script setup lang="ts">
import type {
  BrandStrategyBranch, BrandRoleResult, BigIdeaResult, ChainInputs, DataProvenance,
} from '../types'
import {
  UCard, UBadge, UButton, UIcon, UCheckbox,
  BrandRoleContent, BigIdeaContent, BrandRoleEditForm, BigIdeaEditForm,
  DataProvenanceBadge,
} from '#components'

/** 从 branch 的 brand_role / big_idea 结果里提取 data_provenance */
const branchProvenance = (
  branch: BrandStrategyBranch,
  layer: 'brand_role' | 'big_idea',
): DataProvenance | null => {
  const r = (branch[layer] as { data_provenance?: DataProvenance } | null) ?? null
  return r?.data_provenance ?? null
}

/** 从 branch 的 brand_role / big_idea 结果里提取 chain_inputs */
const branchChainInputs = (
  branch: BrandStrategyBranch,
  layer: 'brand_role' | 'big_idea',
): ChainInputs | null => {
  const r = (branch[layer] as { chain_inputs?: ChainInputs } | null) ?? null
  return r?.chain_inputs ?? null
}

const props = defineProps<{
  branches: BrandStrategyBranch[]
  canEdit: boolean
  canGenerateBrandRole: boolean
  canGenerateBigIdea: boolean
  insightReady: boolean
  generatingBrandRoleAll?: boolean
  generatingBigIdeaAll?: boolean
  regeneratingBrandRoleId?: number | null
  regeneratingBigIdeaId?: number | null
  savingBrandRoleId?: number | null
  savingBigIdeaId?: number | null
}>()

const emit = defineEmits<{
  // tensionIds === undefined → 全跑模式（重置所有分支）
  // tensionIds === number[]  → 子集模式（仅生成这些分支，其他不动）
  'generate-brand-role': [tensionIds: number[] | undefined]
  'generate-big-idea': [tensionIds: number[] | undefined]
  'select-branch': [tensionId: number]
  'regenerate-brand-role': [tensionId: number]
  'regenerate-big-idea': [tensionId: number]
  'save-brand-role': [tensionId: number, result: Record<string, unknown>]
  'save-big-idea': [tensionId: number, result: Record<string, unknown>]
}>()

const { $confirm } = useNuxtApp()

type EditKey = `${'brand_role' | 'big_idea'}:${number}`
const editingMap = ref<Record<EditKey, boolean>>({})
const editRefs = ref<Record<EditKey, { getResult: () => Record<string, unknown> } | null>>({})

const isEditing = (stage: 'brand_role' | 'big_idea', tensionId: number) =>
  !!editingMap.value[`${stage}:${tensionId}`]

const toggleEdit = (stage: 'brand_role' | 'big_idea', tensionId: number) => {
  const key: EditKey = `${stage}:${tensionId}`
  editingMap.value = { ...editingMap.value, [key]: !editingMap.value[key] }
}

const setEditRef = (
  stage: 'brand_role' | 'big_idea',
  tensionId: number,
  el: unknown,
) => {
  const key: EditKey = `${stage}:${tensionId}`
  editRefs.value[key] = el as { getResult: () => Record<string, unknown> } | null
}

const handleSaveBrandRole = (tensionId: number) => {
  const data = editRefs.value[`brand_role:${tensionId}`]?.getResult()
  if (data) {
    editingMap.value = { ...editingMap.value, [`brand_role:${tensionId}`]: false }
    emit('save-brand-role', tensionId, data)
  }
}

const handleSaveBigIdea = (tensionId: number) => {
  const data = editRefs.value[`big_idea:${tensionId}`]?.getResult()
  if (data) {
    editingMap.value = { ...editingMap.value, [`big_idea:${tensionId}`]: false }
    emit('save-big-idea', tensionId, data)
  }
}

const branchCountText = computed(() => {
  const total = props.branches.length
  if (!total) return ''
  const brBranches = props.branches.filter(b => b.brand_role).length
  const biBranches = props.branches.filter(b => b.big_idea).length
  return `${total} 个分支（Brand Role ${brBranches}/${total}，Big Idea ${biBranches}/${total}）`
})

const hasAnyBrandRole = computed(() => props.branches.some(b => b.brand_role))
const hasAnyBigIdea = computed(() => props.branches.some(b => b.big_idea))

// ── 多选状态（用户勾选要生成的 tension 子集）──────────────────────────────────
// 初始：所有分支默认选中（保留 Q2「全跑」默认体验）。
// branches 数组变化时（如 insight 重生成 → 新 tensions），重新初始化为全选。
const selectedTensionIds = ref<Set<number>>(new Set())

watch(
  () => props.branches.map(b => b.tension_id).join(','),
  () => {
    // tensions 列表发生变化 → 重置为全选
    selectedTensionIds.value = new Set(props.branches.map(b => b.tension_id))
  },
  { immediate: true },
)

const isBranchChecked = (tensionId: number) => selectedTensionIds.value.has(tensionId)

const toggleBranchChecked = (tensionId: number) => {
  const s = new Set(selectedTensionIds.value)
  if (s.has(tensionId)) {
    s.delete(tensionId)
  } else {
    s.add(tensionId)
  }
  selectedTensionIds.value = s
}

const checkAll = () => {
  selectedTensionIds.value = new Set(props.branches.map(b => b.tension_id))
}

const uncheckAll = () => {
  selectedTensionIds.value = new Set()
}

// 待生成 brand_role：勾选的 + 未生成 brand_role 的分支
const pendingBrandRoleIds = computed(() =>
  props.branches
    .filter(b => selectedTensionIds.value.has(b.tension_id) && !b.brand_role)
    .map(b => b.tension_id),
)

// 待生成 big_idea：勾选的 + 已有 brand_role + 未生成 big_idea 的分支
const pendingBigIdeaIds = computed(() =>
  props.branches
    .filter(b =>
      selectedTensionIds.value.has(b.tension_id)
      && b.brand_role
      && !b.big_idea,
    )
    .map(b => b.tension_id),
)

// 全选状态判定：用于「全选 / 全不选」按钮 label 切换
const allChecked = computed(() =>
  props.branches.length > 0
  && props.branches.every(b => selectedTensionIds.value.has(b.tension_id)),
)

const anyLoading = computed(() =>
  !!(
    props.generatingBrandRoleAll
    || props.generatingBigIdeaAll
    || props.regeneratingBrandRoleId !== null && props.regeneratingBrandRoleId !== undefined
    || props.regeneratingBigIdeaId !== null && props.regeneratingBigIdeaId !== undefined
  ),
)

const statusLabel = (status: string): string => {
  switch (status) {
    case 'big_idea_done': return '已完成'
    case 'brand_role_done': return 'Brand Role 完成'
    case 'failed': return '失败'
    case 'pending': return '待生成'
    default: return status
  }
}

const statusColor = (status: string): 'success' | 'warning' | 'error' | 'neutral' => {
  switch (status) {
    case 'big_idea_done': return 'success'
    case 'brand_role_done': return 'warning'
    case 'failed': return 'error'
    default: return 'neutral'
  }
}

// 决策：当用户全选了所有分支时，传 undefined 给后端 → 全跑模式（重置所有分支）。
// 部分选择时，传子集 tension_ids → 子集模式（保留未选分支现状）。
const handleGenerateBrandRole = async () => {
  const ids = pendingBrandRoleIds.value
  if (ids.length === 0) return

  const isFullRun = allChecked.value
  // 已存在分支 brand_role 时（重新跑/部分重跑）才需要确认
  if (hasAnyBrandRole.value || !isFullRun) {
    const confirmed = await $confirm({
      title: '确认生成 Brand Role',
      message: isFullRun
        ? `将为全部 ${ids.length} 个分支并行生成 Brand Role（已有结果会被重置，下游 Big Idea 同步作废），确定继续？`
        : `仅对选中的 ${ids.length} 个分支生成 Brand Role，其他分支不动。确定继续？`,
      confirmText: '开始生成',
      type: 'warning',
    })
    if (!confirmed) return
  }

  emit('generate-brand-role', isFullRun ? undefined : ids)
}

const handleGenerateBigIdea = async () => {
  const ids = pendingBigIdeaIds.value
  if (ids.length === 0) return

  // big_idea 全跑判定：选中的 ids 等于所有"已有 brand_role 的分支"
  const allWithBrandRoleIds = props.branches
    .filter(b => b.brand_role)
    .map(b => b.tension_id)
  const isFullRun = allChecked.value
    && allWithBrandRoleIds.every(id => selectedTensionIds.value.has(id))

  if (hasAnyBigIdea.value || !isFullRun) {
    const confirmed = await $confirm({
      title: '确认生成 Big Idea',
      message: isFullRun
        ? `将为已完成 Brand Role 的 ${ids.length} 个分支并行生成 Big Idea（已有结果会被覆盖），确定继续？`
        : `仅对选中的 ${ids.length} 个分支生成 Big Idea，其他分支不动。确定继续？`,
      confirmText: '开始生成',
      type: 'warning',
    })
    if (!confirmed) return
  }

  emit('generate-big-idea', isFullRun ? undefined : ids)
}

const confirmAndEmitBranch = async (
  event: 'regenerate-brand-role' | 'regenerate-big-idea',
  tensionId: number,
  message: string,
) => {
  const confirmed = await $confirm({
    title: '确认重新生成',
    message,
    confirmText: '确认重新生成',
    type: 'warning',
  })
  if (!confirmed) return
  if (event === 'regenerate-brand-role') {
    emit('regenerate-brand-role', tensionId)
  } else {
    emit('regenerate-big-idea', tensionId)
  }
}
</script>
