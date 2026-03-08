<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          to="/strategies"
        />
        <div>
          <ClientOnly>
            <template #fallback>
              <h1 class="text-2xl font-bold text-gray-900 dark:text-white">加载中...</h1>
            </template>
            <div class="flex items-center gap-2">
              <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
                {{ strategy?.name || '加载中...' }}
              </h1>
              <UBadge
                v-if="strategy"
                :color="statusInfo.color"
                variant="soft"
                size="sm"
              >
                {{ statusInfo.label }}
              </UBadge>
            </div>
            <div v-if="strategy" class="flex items-center gap-2 mt-1 text-sm text-gray-500">
              <span>{{ strategy.creator_name }}</span>
              <span>|</span>
              <span>{{ formatDate(strategy.created_at) }}</span>
            </div>
          </ClientOnly>
        </div>
      </div>

      <ClientOnly>
        <div v-if="strategy" class="flex items-center gap-2">
          <UButton
            variant="outline"
            icon="i-heroicons-arrow-down-tray"
            size="sm"
            @click="handleExport"
          >
            导出 Word
          </UButton>
          <UButton
            variant="outline"
            color="error"
            icon="i-heroicons-trash"
            size="sm"
            @click="handleDelete"
          >
            删除
          </UButton>
        </div>
      </ClientOnly>
    </div>

    <!-- 阶段进度指示器 -->
    <ClientOnly>
      <div v-if="strategy" class="flex items-center justify-center gap-0 py-2">
        <template v-for="(stage, i) in STAGES" :key="stage.key">
          <div class="flex flex-col items-center min-w-20">
            <div
              :class="[
                'w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold transition-colors',
                currentStageIndex > i
                  ? 'bg-primary-500 text-white'
                  : currentStageIndex === i
                    ? 'bg-primary-100 text-primary-700 ring-2 ring-primary-500'
                    : 'bg-gray-100 text-gray-400',
              ]"
            >
              <UIcon v-if="currentStageIndex > i" name="i-heroicons-check" class="text-base" />
              <span v-else>{{ stage.key }}</span>
            </div>
            <span
              :class="[
                'text-xs mt-1 text-center',
                currentStageIndex >= i ? 'text-gray-700 dark:text-gray-200' : 'text-gray-400',
              ]"
            >{{ stage.label }}</span>
          </div>
          <div
            v-if="i < STAGES.length - 1"
            :class="[
              'h-0.5 flex-1 mb-4 transition-colors',
              currentStageIndex > i ? 'bg-primary-400' : 'bg-gray-200',
            ]"
          />
        </template>
      </div>
    </ClientOnly>

    <!-- Loading -->
    <div v-if="pending" class="text-center py-16">
      <p class="text-gray-500">加载中...</p>
    </div>

    <ClientOnly v-if="strategy">
      <template #fallback>
        <div class="space-y-4">
          <div v-for="i in 3" :key="i" class="h-48 bg-gray-100 rounded-lg animate-pulse" />
        </div>
      </template>

      <!-- ===== 阶段 A: 监测规划 ===== -->
      <UCard>
        <template #header>
          <div class="flex items-center gap-2">
            <span class="font-bold text-primary-600">A</span>
            <h2 class="text-lg font-semibold">监测规划</h2>
          </div>
        </template>

        <!-- Brand Brief 摘要 -->
        <div
          v-if="strategy.brand_brief"
          class="mb-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm"
        >
          <!-- 只读模式 -->
          <div v-if="!editingBrief">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <span class="font-medium">{{ strategy.brand_brief.brand_name }}</span>
                <span class="text-gray-400 mx-1.5">·</span>
                <span class="text-gray-600 dark:text-gray-400">{{ strategy.brand_brief.analysis_goal }}</span>
              </div>
              <UButton
                variant="ghost"
                size="xs"
                icon="i-heroicons-pencil-square"
                class="shrink-0"
                @click="startEditBrief"
              />
            </div>
            <div v-if="strategy.brand_brief.constraints" class="text-gray-400 mt-1">
              {{ strategy.brand_brief.constraints }}
            </div>
          </div>
          <!-- 编辑模式 -->
          <div v-else class="flex flex-col gap-3">
            <div>
              <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">品牌名称</label>
              <UInput
                v-model="editBrief.brand_name"
                placeholder="输入品牌或产品名称"
                size="sm"
                class="w-full"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">分析目标</label>
              <UTextarea
                v-model="editBrief.analysis_goal"
                placeholder="描述分析目标，例如：了解品牌在社交媒体上的口碑和竞争格局"
                :rows="2"
                size="sm"
                class="w-full"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">补充说明（可选）</label>
              <UTextarea
                v-model="editBrief.constraints"
                placeholder="例如：重点关注某些竞品、特定时间段、排除某些话题..."
                :rows="2"
                size="sm"
                class="w-full"
              />
            </div>
            <div
              v-if="latestMonitorSuggestions.length"
              class="text-xs text-amber-600 dark:text-amber-400"
            >
              保存后将自动重新生成监测方案
            </div>
            <div class="flex items-center gap-2">
              <UButton
                size="xs"
                :loading="savingBrief"
                :disabled="!editBrief.brand_name.trim() || !editBrief.analysis_goal.trim()"
                @click="handleSaveBrief"
              >
                保存
              </UButton>
              <UButton
                size="xs"
                variant="ghost"
                @click="editingBrief = false"
              >
                取消
              </UButton>
            </div>
          </div>
        </div>

        <!-- 未生成方案：显示生成按钮 -->
        <div v-if="!latestMonitorSuggestions.length">
          <UTextarea
            v-model="consultInput"
            placeholder="（可选）补充说明，例如: 重点看抖音和小红书、关注某个竞品..."
            :rows="2"
            class="w-full mb-3"
          />
          <UButton
            :loading="consultLoading"
            icon="i-heroicons-sparkles"
            @click="handleConsult"
          >
            生成监测方案
          </UButton>
        </div>

        <!-- 已有方案：展示建议列表（可编辑） -->
        <div v-else>
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-medium text-gray-600 dark:text-gray-400">
              AI 推荐方案
            </h3>
            <UButton
              v-if="!editingPlan"
              variant="ghost"
              size="xs"
              icon="i-heroicons-pencil-square"
              @click="editingPlan = true"
            >
              编辑方案
            </UButton>
            <UButton
              v-else
              variant="ghost"
              size="xs"
              icon="i-heroicons-check"
              @click="editingPlan = false"
            >
              完成编辑
            </UButton>
          </div>

          <!-- AI 需求理解 -->
          <div
            v-if="latestUnderstandingSummary"
            class="mb-3 p-2.5 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-700 dark:text-blue-300"
          >
            <span class="font-medium">AI 理解：</span>{{ latestUnderstandingSummary }}
          </div>

          <!-- 采集建议 -->
          <h4 class="text-xs font-medium text-gray-500 mb-2">
            采集建议（{{ editableSuggestions.length }} 个监测）
          </h4>
          <MonitorSuggestionsEditor
            v-model="editableSuggestions"
            v-model:notes-per-task="notesPerTask"
            :editing="editingPlan"
          />

          <!-- 切片建议 -->
          <div v-if="editableSlicePlan.length" class="mb-4">
            <h4 class="text-xs font-medium text-gray-500 mb-2">
              切片建议（{{ editableSlicePlan.length }} 个切片）
            </h4>
            <SlicePlanEditor
              v-model="editableSlicePlan"
              :editing="editingPlan"
            />
          </div>

          <div class="flex items-center gap-3">
            <UButton
              :loading="confirmPlanLoading"
              icon="i-heroicons-check-circle"
              @click="handleConfirmPlan"
            >
              {{ strategy.suggested_monitor_ids?.length ? '重新创建监测' : '确认并创建监测' }}
            </UButton>
            <UButton
              variant="outline"
              :loading="consultLoading"
              icon="i-heroicons-arrow-path"
              @click="handleConsult"
            >
              重新生成方案
            </UButton>
          </div>
        </div>

        <!-- 监测已创建提示 -->
        <div
          v-if="strategy.suggested_monitor_ids?.length"
          class="mt-4 flex items-start gap-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg"
        >
          <UIcon name="i-heroicons-information-circle" class="text-blue-500 mt-0.5 shrink-0 text-lg" />
          <div class="text-sm text-blue-700 dark:text-blue-300 space-y-1">
            <p>已创建 {{ strategy.suggested_monitor_ids.length }} 个监测，采集任务自动进行中。完成后前往监测项目创建切片。</p>
            <UButton variant="link" size="xs" :to="monitorPageLink" class="p-0">
              前往监测项目
            </UButton>
          </div>
        </div>
      </UCard>

      <!-- ===== 阶段 B: 数据评估 ===== -->
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="font-bold text-primary-600">B</span>
              <h2 class="text-lg font-semibold">数据评估</h2>
            </div>
            <span class="text-sm text-gray-500">{{ strategy.slices.length }} 个切片</span>
          </div>
        </template>

        <!-- 已关联切片列表 -->
        <div v-if="strategy.slices.length" class="mb-4">
          <div class="space-y-1">
            <div
              v-for="s in strategy.slices"
              :key="s.slice_id"
              class="flex items-center gap-2 text-sm py-1.5 border-b border-gray-100 dark:border-gray-800 last:border-0"
            >
              <UIcon name="i-heroicons-document-chart-bar" class="text-gray-400 shrink-0" />
              <NuxtLink
                :to="`/social-media/monitors/${s.monitor_id}/analysis?slice_id=${s.slice_id}`"
                class="flex items-center gap-1 hover:text-primary-600 transition-colors"
              >
                <span class="text-gray-600 dark:text-gray-400">{{ s.monitor_name }}</span>
                <span class="text-gray-300">/</span>
                <span class="font-medium">{{ s.slice_name || `切片 #${s.slice_id}` }}</span>
              </NuxtLink>
              <div class="flex-1" />
              <UButton
                variant="ghost"
                size="xs"
                color="error"
                icon="i-heroicons-x-mark"
                @click="handleRemoveSlice(s.slice_id)"
              />
            </div>
          </div>
        </div>
        <div v-else class="mb-4 text-sm text-gray-400">
          暂未关联任何切片
        </div>

        <!-- 添加切片 -->
        <div class="mb-4">
          <UButton
            variant="outline"
            size="sm"
            icon="i-heroicons-plus"
            @click="showAddSlices = !showAddSlices"
          >
            添加切片
          </UButton>

          <div v-if="showAddSlices" class="mt-3 border border-gray-200 dark:border-gray-700 rounded-lg p-3">
            <div v-if="addMonitorsPending" class="text-sm text-gray-400 py-2">加载监测列表...</div>
            <div v-else-if="addMonitors.length === 0" class="text-sm text-gray-400 py-2">暂无监测</div>
            <div v-else class="space-y-2 max-h-64 overflow-y-auto">
              <div
                v-for="monitor in addMonitors"
                :key="monitor.id"
                class="border border-gray-100 dark:border-gray-700 rounded"
              >
                <button
                  class="w-full flex items-center justify-between p-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
                  @click="toggleAddMonitor(monitor.id)"
                >
                  <div class="flex items-center gap-1">
                    <UIcon
                      :name="addExpandedMonitors.has(monitor.id) ? 'i-heroicons-chevron-down' : 'i-heroicons-chevron-right'"
                      class="text-gray-400 text-xs"
                    />
                    <span>{{ monitor.name }}</span>
                  </div>
                </button>
                <div
                  v-if="addExpandedMonitors.has(monitor.id)"
                  class="border-t border-gray-100 dark:border-gray-700 p-2 space-y-1"
                >
                  <div
                    v-if="!addMonitorSlicesMap[monitor.id]?.length"
                    class="text-xs text-gray-400 py-1"
                  >
                    该监测暂无分析切片
                  </div>
                  <label
                    v-for="slice in (addMonitorSlicesMap[monitor.id] || [])"
                    :key="slice.id"
                    class="flex items-center gap-2 p-1.5 rounded hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer text-sm"
                  >
                    <input
                      type="checkbox"
                      :checked="selectedAddSliceIds.includes(slice.id)"
                      class="rounded border-gray-300"
                      :disabled="isSliceAlreadyLinked(slice.id)"
                      @change="toggleAddSlice(slice.id)"
                    >
                    <span :class="isSliceAlreadyLinked(slice.id) ? 'text-gray-400' : ''">
                      {{ slice.name || `切片 #${slice.id}` }}
                    </span>
                    <span v-if="isSliceAlreadyLinked(slice.id)" class="text-xs text-gray-400">已关联</span>
                  </label>
                </div>
              </div>
            </div>
            <div class="flex items-center gap-2 mt-3">
              <UButton
                size="sm"
                :loading="addSlicesLoading"
                :disabled="selectedAddSliceIds.length === 0"
                @click="handleAddSlices"
              >
                确认关联 {{ selectedAddSliceIds.length > 0 ? `(${selectedAddSliceIds.length})` : '' }}
              </UButton>
              <UButton size="sm" variant="ghost" @click="showAddSlices = false">
                取消
              </UButton>
            </div>
          </div>
        </div>

        <!-- AI 评估 -->
        <div class="mb-4">
          <UButton
            :loading="evaluateLoading"
            variant="outline"
            icon="i-heroicons-magnifying-glass"
            @click="handleEvaluate"
          >
            AI 评估充分性
          </UButton>
        </div>

        <!-- 评估结果 -->
        <div
          v-if="strategy.evaluation_result"
          class="mb-4 p-3 rounded-lg border"
          :class="strategy.evaluation_result.is_sufficient
            ? 'border-green-200 bg-green-50 dark:bg-green-900/20'
            : 'border-amber-200 bg-amber-50 dark:bg-amber-900/20'"
        >
          <div class="flex items-center gap-2 mb-2">
            <UIcon
              :name="strategy.evaluation_result.is_sufficient ? 'i-heroicons-check-circle' : 'i-heroicons-exclamation-triangle'"
              :class="strategy.evaluation_result.is_sufficient ? 'text-green-500' : 'text-amber-500'"
            />
            <span class="font-medium text-sm">
              综合评分 {{ Math.round(strategy.evaluation_result.overall_score * 100) }}%
              ·
              {{ strategy.evaluation_result.is_sufficient ? '数据充分' : '数据待补充' }}
            </span>
          </div>
          <div v-if="strategy.evaluation_result.gap_analysis?.length" class="space-y-1">
            <div
              v-for="(gap, i) in strategy.evaluation_result.gap_analysis"
              :key="i"
              class="text-xs text-gray-600 dark:text-gray-400"
            >
              · {{ gap.description }}
            </div>
          </div>
          <!-- 切片建议 -->
          <div v-if="strategy.evaluation_result.slice_suggestions?.length" class="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
            <h4 class="text-xs font-medium text-gray-500 mb-1.5">切片优化建议</h4>
            <div class="space-y-1.5">
              <div
                v-for="(ss, i) in strategy.evaluation_result.slice_suggestions"
                :key="i"
                class="text-xs text-gray-600 dark:text-gray-400"
              >
                <span class="font-medium">{{ ss.slice_name }}</span>：{{ ss.issue }}
                <span v-if="ss.suggestion" class="text-gray-500"> → {{ ss.suggestion }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 结构优化分析 -->
        <div
          v-if="strategy.evaluation_result?.structure_analysis"
          class="mb-4 p-3 rounded-lg border border-indigo-200 bg-indigo-50 dark:bg-indigo-900/20"
        >
          <div class="flex items-center gap-2 mb-2">
            <UIcon name="i-heroicons-squares-2x2" class="text-indigo-500 shrink-0" />
            <span class="font-medium text-sm text-indigo-700 dark:text-indigo-300">切片结构分析</span>
          </div>
          <p class="text-xs text-indigo-700 dark:text-indigo-300 mb-3">
            {{ strategy.evaluation_result.structure_analysis.summary }}
          </p>

          <!-- 已有切片问题 -->
          <div
            v-if="strategy.evaluation_result.structure_analysis.current_slice_issues?.length"
            class="mb-3"
          >
            <h4 class="text-xs font-medium text-gray-500 mb-1.5">切片结构问题</h4>
            <div class="space-y-1.5">
              <div
                v-for="(issue, i) in strategy.evaluation_result.structure_analysis.current_slice_issues"
                :key="i"
                class="text-xs text-gray-600 dark:text-gray-400"
              >
                <span class="font-medium">{{ issue.slice_name }}</span>：{{ issue.description }}
                <span class="text-gray-500"> → {{ issue.suggestion }}</span>
              </div>
            </div>
          </div>

          <!-- 未利用的数据机会 -->
          <div
            v-if="strategy.evaluation_result.structure_analysis.unused_opportunities?.length"
            class="mb-3"
          >
            <h4 class="text-xs font-medium text-gray-500 mb-1.5">可关联的现有数据</h4>
            <div class="space-y-1.5">
              <div
                v-for="(opp, i) in strategy.evaluation_result.structure_analysis.unused_opportunities"
                :key="i"
                class="text-xs text-gray-600 dark:text-gray-400"
              >
                <span class="font-medium text-indigo-600 dark:text-indigo-400">
                  {{ opp.monitor_name }} / {{ opp.slice_name }}
                </span>
                <span class="text-gray-400 mx-1">·</span>{{ opp.why_valuable }}
                <span v-if="opp.gap_addressed" class="text-gray-400 ml-1">（填补：{{ opp.gap_addressed }}）</span>
              </div>
            </div>
          </div>

          <!-- 推荐最终结构 -->
          <div v-if="strategy.evaluation_result.structure_analysis.recommended_structure?.length">
            <h4 class="text-xs font-medium text-gray-500 mb-1.5">
              推荐切片组合（{{ strategy.evaluation_result.structure_analysis.recommended_structure.length }} 个）
            </h4>
            <div class="space-y-1.5">
              <div
                v-for="(rec, i) in strategy.evaluation_result.structure_analysis.recommended_structure"
                :key="i"
                class="text-xs"
              >
                <div class="flex items-center gap-1.5">
                  <UBadge
                    :color="rec.action === 'keep' ? 'success' : rec.action === 'associate' ? 'info' : rec.action === 'adjust' ? 'warning' : 'neutral'"
                    variant="soft"
                    size="xs"
                  >
                    {{ { keep: '保留', associate: '关联', adjust: '调整', supplement: '待补充' }[rec.action] }}
                  </UBadge>
                  <span class="font-medium text-gray-700 dark:text-gray-300">{{ rec.name }}</span>
                  <span class="text-gray-400">{{ rec.mode }}</span>
                </div>
                <p class="text-gray-500 mt-0.5 ml-0.5">{{ rec.purpose }}</p>
                <p v-if="rec.action_detail" class="text-gray-400 mt-0.5 ml-0.5 italic">
                  操作：{{ rec.action_detail }}
                </p>
              </div>
            </div>
          </div>

          <!-- 底部提示：仍需采集 / 或已有数据够用不必补采 -->
          <div
            class="mt-2 pt-2 border-t border-indigo-200 dark:border-indigo-700 text-xs"
          >
            <!-- 仍需采集 -->
            <div
              v-if="strategy.evaluation_result.structure_analysis.collection_still_needed && strategy.evaluation_result.structure_analysis.collection_note"
              class="text-indigo-600 dark:text-indigo-400"
            >
              <UIcon name="i-heroicons-information-circle" class="inline mr-1" />
              {{ strategy.evaluation_result.structure_analysis.collection_note }}
            </div>
            <!-- 已有数据可覆盖缺口，无需补采 -->
            <div
              v-else-if="!strategy.evaluation_result.structure_analysis.collection_still_needed && strategy.evaluation_result.supplementary_suggestions?.length"
              class="text-green-600 dark:text-green-400"
            >
              <UIcon name="i-heroicons-check-circle" class="inline mr-1" />
              已有数据可覆盖当前缺口，按上方推荐切片组合关联即可，无需补充采集。
            </div>
          </div>
        </div>

        <!-- 补充采集: 状态 1 - 评估不足 + 有建议 + 未确认补充 -->
        <div v-if="showSupplementaryEditor">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-medium text-gray-600 dark:text-gray-400">
              补充采集建议（{{ editableSupplementary.length }} 条）
            </h3>
            <UButton
              v-if="!editingSupplementary"
              variant="ghost"
              size="xs"
              icon="i-heroicons-pencil-square"
              @click="editingSupplementary = true"
            >
              编辑
            </UButton>
            <UButton
              v-else
              variant="ghost"
              size="xs"
              icon="i-heroicons-check"
              @click="editingSupplementary = false"
            >
              完成编辑
            </UButton>
          </div>

          <MonitorSuggestionsEditor
            v-model="editableSupplementary"
            v-model:notes-per-task="supplementaryNotesPerTask"
            :editing="editingSupplementary"
          />

          <!-- 补充切片建议 -->
          <div v-if="editableSupplementarySlicePlan.length" class="mb-4">
            <h4 class="text-xs font-medium text-gray-500 mb-2">
              切片建议（{{ editableSupplementarySlicePlan.length }} 个切片）
            </h4>
            <SlicePlanEditor
              v-model="editableSupplementarySlicePlan"
              :editing="editingSupplementary"
            />
          </div>

          <UButton
            :loading="confirmSupplementaryLoading"
            icon="i-heroicons-check-circle"
            @click="handleConfirmSupplementary"
          >
            确认补充采集
          </UButton>
        </div>

        <!-- 补充采集: 已确认，显示只读方案 + 前往监测提示 -->
        <div v-if="showSupplementaryConfirmed">
          <!-- 已确认的方案（只读） -->
          <div v-if="confirmedSupplementarySuggestions.length" class="mb-3">
            <h4 class="text-xs font-medium text-gray-500 mb-2">
              已确认的补充采集方案（{{ confirmedSupplementarySuggestions.length }} 条）
            </h4>
            <MonitorSuggestionsEditor
              :model-value="confirmedSupplementarySuggestions"
              :notes-per-task="supplementaryNotesPerTask"
              :editing="false"
            />
          </div>
          <div v-if="confirmedSupplementarySlicePlan.length" class="mb-3">
            <h4 class="text-xs font-medium text-gray-500 mb-2">
              切片建议（{{ confirmedSupplementarySlicePlan.length }} 个切片）
            </h4>
            <SlicePlanEditor
              :model-value="confirmedSupplementarySlicePlan"
              :editing="false"
            />
          </div>

          <div class="mb-4 p-3 border border-blue-200 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
            <div class="flex items-start gap-2 text-sm">
              <UIcon name="i-heroicons-information-circle" class="text-blue-500 mt-0.5 shrink-0" />
              <div class="text-blue-700 dark:text-blue-300 space-y-1">
                <p>补充采集任务已提交，请前往监测项目查看进度。完成后创建/调整切片，回来关联并重新评估。</p>
                <UButton
                  variant="link"
                  size="xs"
                  :to="monitorPageLink"
                  class="p-0"
                >
                  前往监测项目
                </UButton>
              </div>
            </div>
          </div>
        </div>

        <!-- 确认就绪 -->
        <div class="pt-4 mt-2 border-t border-gray-100 dark:border-gray-800 flex items-center gap-3">
          <UButton
            :loading="confirmReadyLoading"
            icon="i-heroicons-rocket-launch"
            :disabled="strategy.status === 'completed'"
            @click="handleConfirmReady"
          >
            确认数据就绪，进入策略生成
          </UButton>
          <span
            v-if="['slices_ready', 'phase1_done', 'phase2_done', 'completed'].includes(strategy.status)"
            class="text-sm text-green-600 dark:text-green-400"
          >
            已就绪
          </span>
        </div>
      </UCard>

      <!-- ===== 阶段 C: 策略生成 ===== -->
      <div class="space-y-4">
        <div class="flex items-center gap-2">
          <span class="font-bold text-primary-600">C</span>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">策略生成</h2>
        </div>

        <!-- Phase 1: 洞察层 -->
        <StrategyPhaseCard
          :phase="1"
          title="洞察层"
          :has-result="!!strategy.phase1_result"
          :can-generate="true"
          :can-edit="true"
          :generating="generatingPhase === 1"
          :saving="savingPhase === 1"
          :result="strategy.phase1_result"
          @generate="handleGenerate(1)"
          @save="(r: Record<string, unknown>) => handleSavePhase(1, r)"
        >
          <Phase1Content :result="phase1Data" />
        </StrategyPhaseCard>

        <!-- Phase 2: 策略层 -->
        <StrategyPhaseCard
          :phase="2"
          title="策略层"
          :has-result="!!strategy.phase2_result"
          :can-generate="canGeneratePhase2"
          :can-edit="true"
          :generating="generatingPhase === 2"
          :saving="savingPhase === 2"
          :result="strategy.phase2_result"
          @generate="handleGenerate(2)"
          @save="(r: Record<string, unknown>) => handleSavePhase(2, r)"
        >
          <Phase2Content :result="phase2Data" />
        </StrategyPhaseCard>

        <!-- Phase 3: 创意层 -->
        <StrategyPhaseCard
          :phase="3"
          title="创意层"
          :has-result="!!strategy.phase3_result"
          :can-generate="canGeneratePhase3"
          :can-edit="true"
          :generating="generatingPhase === 3"
          :saving="savingPhase === 3"
          :result="strategy.phase3_result"
          @generate="handleGenerate(3)"
          @save="(r: Record<string, unknown>) => handleSavePhase(3, r)"
        >
          <Phase3Content :result="phase3Data" />
        </StrategyPhaseCard>
      </div>
    </ClientOnly>
  </div>
</template>

<script setup lang="ts">
import type {
  StrategyStatus,
  Phase1Result,
  Phase2Result,
  Phase3Result,
  MonitorSuggestion,
  SlicePlanItem,
} from '../../../types'
import { UBadge, UButton } from '#components'

definePageMeta({ title: '策略详情' })

// ── 阶段定义 ──────────────────────────────────────────────────────────────────

const STAGES = [
  { key: 'A', label: '监测规划' },
  { key: 'B', label: '数据评估' },
  { key: 'C', label: '策略生成' },
] as const

const STATUS_MAP: Record<StrategyStatus, { label: string; color: 'neutral' | 'info' | 'warning' | 'success' }> = {
  briefing: { label: '需求阶段', color: 'neutral' },
  consulting: { label: '咨询中', color: 'info' },
  monitors_created: { label: '监测已创建', color: 'info' },
  slices_ready: { label: '数据就绪', color: 'warning' },
  phase1_done: { label: '洞察完成', color: 'warning' },
  phase2_done: { label: '策略完成', color: 'warning' },
  completed: { label: '已完成', color: 'success' },
}

const STATUS_ORDER: Record<StrategyStatus, number> = {
  briefing: 0, consulting: 1, monitors_created: 2,
  slices_ready: 3, phase1_done: 4, phase2_done: 5, completed: 6,
}


// ── 基础数据 ──────────────────────────────────────────────────────────────────

const route = useRoute()
const strategiesApi = useStrategies()
const { apiRequest, useApiData: useApiDataFn } = useApi()

const strategyId = computed(() => Number(route.params.id))
const { data: strategy, pending } = strategiesApi.getStrategy(strategyId)

// ── 状态计算 ──────────────────────────────────────────────────────────────────

const statusInfo = computed(() => {
  const s = strategy.value?.status as StrategyStatus
  return STATUS_MAP[s] || { label: s, color: 'neutral' as const }
})

const currentStatusOrder = computed(() => {
  const s = strategy.value?.status as StrategyStatus
  return STATUS_ORDER[s] ?? 0
})

const currentStageIndex = computed(() => {
  const o = currentStatusOrder.value
  if (o <= 1) return 0   // briefing, consulting → A
  if (o <= 2) return 1   // monitors_created → B
  return 2               // slices_ready, phase1_done, phase2_done, completed → C
})

const canGeneratePhase2 = computed(() => currentStatusOrder.value >= STATUS_ORDER.phase1_done)
const canGeneratePhase3 = computed(() => currentStatusOrder.value >= STATUS_ORDER.phase2_done)

const phase1Data = computed(() => (strategy.value?.phase1_result || null) as Phase1Result | null)
const phase2Data = computed(() => (strategy.value?.phase2_result || null) as Phase2Result | null)
const phase3Data = computed(() => (strategy.value?.phase3_result || null) as Phase3Result | null)

const latestMonitorSuggestions = computed<MonitorSuggestion[]>(() => {
  const rounds = strategy.value?.consultation_rounds
  if (!rounds?.length) return []
  return rounds[0]?.ai_response?.monitor_suggestions ?? []
})

const latestSlicePlan = computed<SlicePlanItem[]>(() => {
  const rounds = strategy.value?.consultation_rounds
  if (!rounds?.length) return []
  return rounds[0]?.ai_response?.slice_plan ?? []
})

const latestUnderstandingSummary = computed(() => {
  const rounds = strategy.value?.consultation_rounds
  if (!rounds?.length) return ''
  return rounds[0]?.ai_response?.understanding_summary ?? ''
})

// ── Panel A: 监测规划 ────────────────────────────────────────────────────────

// Panel A: Brief 编辑
const editingBrief = ref(false)
const editBrief = ref({ brand_name: '', analysis_goal: '', constraints: '' })
const savingBrief = ref(false)

const startEditBrief = () => {
  const b = strategy.value?.brand_brief
  editBrief.value = {
    brand_name: b?.brand_name || '',
    analysis_goal: b?.analysis_goal || '',
    constraints: b?.constraints || '',
  }
  editingBrief.value = true
}

const handleSaveBrief = async () => {
  if (!editBrief.value.brand_name.trim() || !editBrief.value.analysis_goal.trim()) return
  savingBrief.value = true
  try {
    await strategiesApi.updateStrategy(strategyId.value, {
      brand_brief: {
        ...strategy.value?.brand_brief,
        brand_name: editBrief.value.brand_name.trim(),
        analysis_goal: editBrief.value.analysis_goal.trim(),
        constraints: editBrief.value.constraints.trim() || undefined,
      },
    })
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
    editingBrief.value = false
    // Brief 变更后自动重新生成监测方案
    if (latestMonitorSuggestions.value.length) {
      await handleConsult()
    }
  } catch {
    // 错误已由 useApi 处理
  } finally {
    savingBrief.value = false
  }
}

const consultInput = ref('')
const consultLoading = ref(false)
const confirmPlanLoading = ref(false)
const editingPlan = ref(false)
const editableSuggestions = ref<MonitorSuggestion[]>([])
const editableSlicePlan = ref<SlicePlanItem[]>([])
const notesPerTask = ref(50)

// AI 方案加载后初始化可编辑副本
watch(latestMonitorSuggestions, (suggestions) => {
  if (suggestions.length && !editableSuggestions.value.length) {
    editableSuggestions.value = suggestions.map(s => ({ ...s }))
  }
}, { immediate: true })

watch(latestSlicePlan, (plan) => {
  if (plan.length && !editableSlicePlan.value.length) {
    editableSlicePlan.value = plan.map(p => ({ ...p }))
  }
}, { immediate: true })

// 新创建的策略自动生成监测方案
watch(() => strategy.value, (s) => {
  if (s && s.status === 'briefing' && !s.consultation_rounds?.length) {
    handleConsult()
  }
}, { once: true })

const handleConsult = async () => {
  consultLoading.value = true
  try {
    await strategiesApi.consult(strategyId.value, consultInput.value.trim())
    consultInput.value = ''
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
    // 重新初始化可编辑副本
    editableSuggestions.value = latestMonitorSuggestions.value.map(s => ({ ...s }))
    editableSlicePlan.value = latestSlicePlan.value.map(p => ({ ...p }))
    editingPlan.value = false
  } catch {
    // 错误已由 useApi 处理
  } finally {
    consultLoading.value = false
  }
}

const handleConfirmPlan = async () => {
  if (!editableSuggestions.value.length) return
  confirmPlanLoading.value = true
  try {
    await strategiesApi.confirmPlan(
      strategyId.value,
      editableSuggestions.value,
      notesPerTask.value,
      editableSlicePlan.value.length ? editableSlicePlan.value : undefined,
    )
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
    editingPlan.value = false
  } catch {
    // 错误已由 useApi 处理
  } finally {
    confirmPlanLoading.value = false
  }
}

// ── Panel B: 切片 + 评估 ──────────────────────────────────────────────────────

interface AddMonitorItem { id: number; name: string }
interface AddSliceItem { id: number; name: string | null; monitor_id: number; created_at: string }

const showAddSlices = ref(false)
const addExpandedMonitors = ref(new Set<number>())
const addMonitorSlicesMap = ref<Record<number, AddSliceItem[]>>({})
const selectedAddSliceIds = ref<number[]>([])
const addSlicesLoading = ref(false)
const evaluateLoading = ref(false)
const confirmReadyLoading = ref(false)

const { data: addMonitorsData, pending: addMonitorsPending } = useApiDataFn<{
  items: AddMonitorItem[]
}>('/social-media/monitors?page_size=100', { key: 'strategy-detail-monitors' })

const addMonitors = computed(() => addMonitorsData.value?.items || [])

const handleRemoveSlice = async (sliceId: number) => {
  try {
    await strategiesApi.removeSlice(strategyId.value, sliceId)
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
  } catch {
    // 错误已由 useApi 处理
  }
}

const isSliceAlreadyLinked = (sliceId: number) => {
  return strategy.value?.slices.some(s => s.slice_id === sliceId) ?? false
}

const toggleAddMonitor = async (monitorId: number) => {
  if (addExpandedMonitors.value.has(monitorId)) {
    addExpandedMonitors.value.delete(monitorId)
  } else {
    addExpandedMonitors.value.add(monitorId)
    if (!addMonitorSlicesMap.value[monitorId]) {
      try {
        const result = await apiRequest<{ items: AddSliceItem[] }>(
          `/social-media/analysis/monitors/${monitorId}/slices`
        )
        addMonitorSlicesMap.value = { ...addMonitorSlicesMap.value, [monitorId]: result.items }
      } catch {
        addMonitorSlicesMap.value = { ...addMonitorSlicesMap.value, [monitorId]: [] }
      }
    }
  }
}

const toggleAddSlice = (sliceId: number) => {
  const idx = selectedAddSliceIds.value.indexOf(sliceId)
  if (idx >= 0) {
    selectedAddSliceIds.value = selectedAddSliceIds.value.filter(id => id !== sliceId)
  } else {
    selectedAddSliceIds.value = [...selectedAddSliceIds.value, sliceId]
  }
}

const handleAddSlices = async () => {
  if (!selectedAddSliceIds.value.length) return
  addSlicesLoading.value = true
  try {
    await strategiesApi.addSlices(strategyId.value, selectedAddSliceIds.value)
    selectedAddSliceIds.value = []
    showAddSlices.value = false
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    addSlicesLoading.value = false
  }
}

const handleEvaluate = async () => {
  evaluateLoading.value = true
  editableSupplementary.value = []
  editableSupplementarySlicePlan.value = []
  try {
    await strategiesApi.evaluate(strategyId.value)
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    evaluateLoading.value = false
  }
}

const handleConfirmReady = async () => {
  confirmReadyLoading.value = true
  try {
    await strategiesApi.confirmReady(strategyId.value)
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    confirmReadyLoading.value = false
  }
}

// ── Panel B: 补充采集 ────────────────────────────────────────────────────────

const editableSupplementary = ref<MonitorSuggestion[]>([])
const editableSupplementarySlicePlan = ref<SlicePlanItem[]>([])
const editingSupplementary = ref(false)
const supplementaryNotesPerTask = ref(50)
const confirmSupplementaryLoading = ref(false)

const pendingSupplementaryTaskIds = computed(() =>
  strategy.value?.evaluation_result?.pending_supplementary_task_ids || [],
)

const hasSupplementarySuggestions = computed(() => {
  const sug = strategy.value?.evaluation_result?.supplementary_suggestions
  return Array.isArray(sug) && sug.length > 0
})

// 已确认的补充方案（只读展示，从 evaluation_result 原始数据读取）
const confirmedSupplementarySuggestions = computed<MonitorSuggestion[]>(() => {
  const sug = strategy.value?.evaluation_result?.supplementary_suggestions
  return Array.isArray(sug) ? sug : []
})

const confirmedSupplementarySlicePlan = computed<SlicePlanItem[]>(() => {
  const plan = strategy.value?.evaluation_result?.supplementary_slice_plan
  return Array.isArray(plan) ? plan : []
})

const showSupplementaryEditor = computed(() => {
  if (!strategy.value?.evaluation_result) return false
  if (!hasSupplementarySuggestions.value) return false
  if (pendingSupplementaryTaskIds.value.length > 0) return false
  // Architect 已找到现有数据可填补缺口，不需要补充采集
  if (strategy.value.evaluation_result.structure_analysis?.collection_still_needed === false) return false
  return true
})

const showSupplementaryConfirmed = computed(() => {
  return pendingSupplementaryTaskIds.value.length > 0
})

const monitorPageLink = computed(() => {
  const monitorIds = strategy.value?.suggested_monitor_ids || []
  if (monitorIds.length > 0) {
    return `/social-media/monitors/${monitorIds[0]}`
  }
  return '/social-media/monitors'
})

// Initialize editable supplementary from evaluation result
// 无条件覆盖：每次评估结果变化（包括重新评估）都刷新编辑器
watch(() => strategy.value?.evaluation_result?.supplementary_suggestions, (suggestions) => {
  editableSupplementary.value = suggestions?.length ? suggestions.map(s => ({ ...s })) : []
}, { immediate: true })

watch(() => strategy.value?.evaluation_result?.supplementary_slice_plan, (plan) => {
  editableSupplementarySlicePlan.value = plan?.length ? plan.map(p => ({ ...p })) : []
}, { immediate: true })

const handleConfirmSupplementary = async () => {
  if (!editableSupplementary.value.length) return
  confirmSupplementaryLoading.value = true
  try {
    await strategiesApi.confirmSupplementary(
      strategyId.value,
      editableSupplementary.value,
      supplementaryNotesPerTask.value,
    )
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
    editableSupplementary.value = []
    editableSupplementarySlicePlan.value = []
  } catch {
    // 错误已由 useApi 处理
  } finally {
    confirmSupplementaryLoading.value = false
  }
}

// ── Panel C: Phase 生成 ───────────────────────────────────────────────────────

const generatingPhase = ref<1 | 2 | 3 | null>(null)
const savingPhase = ref<1 | 2 | 3 | null>(null)

const handleGenerate = async (phase: 1 | 2 | 3) => {
  generatingPhase.value = phase
  try {
    await strategiesApi.generatePhase(strategyId.value, phase)
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    generatingPhase.value = null
  }
}

const handleSavePhase = async (phase: 1 | 2 | 3, result: Record<string, unknown>) => {
  savingPhase.value = phase
  try {
    await strategiesApi.editPhase(strategyId.value, phase, result)
    strategy.value = await strategiesApi.fetchStrategy(strategyId.value)
  } catch {
    // 错误已由 useApi 处理
  } finally {
    savingPhase.value = null
  }
}

// ── 工具函数 ────────────────────────────────────────────────────────────────────

const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const handleExport = async () => {
  if (!strategy.value) return
  try {
    await strategiesApi.exportStrategy(strategyId.value, strategy.value.name)
  } catch {
    // 错误已由 useApi 处理
  }
}

const handleDelete = async () => {
  if (!strategy.value) return
  try {
    const { $confirm } = useNuxtApp()
    const confirmed = await $confirm(`确定要删除策略「${strategy.value.name}」吗？`)
    if (!confirmed) return

    await strategiesApi.deleteStrategy(strategyId.value)
    navigateTo('/strategies')
  } catch {
    // 错误已由 useApi 处理
  }
}
</script>
