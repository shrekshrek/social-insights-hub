<template>
  <div class="space-y-3">
    <!-- 当前参与者列表 -->
    <div class="flex flex-wrap gap-2 min-h-8">
      <span
        v-if="!currentParticipants.length"
        class="text-sm text-gray-400 dark:text-gray-500 italic"
      >
        暂无参与者
      </span>
      <UBadge
        v-for="p in currentParticipants"
        :key="p.id"
        color="primary"
        variant="soft"
        class="flex items-center gap-1 pr-1"
      >
        {{ p.username }}
        <button
          v-if="canManage"
          class="ml-1 hover:text-red-500 transition-colors"
          :title="`移除 ${p.username}`"
          @click="handleRemove(p.id)"
        >
          <UIcon name="i-heroicons-x-mark" class="size-3" />
        </button>
      </UBadge>
    </div>

    <!-- 添加参与者（仅 owner 可见） -->
    <div v-if="canManage" class="flex gap-2">
      <USelectMenu
        v-model="selectedUserIds"
        :items="availableUsers"
        multiple
        value-key="id"
        label-key="username"
        placeholder="搜索并选择用户..."
        :search-attributes="['username']"
        class="flex-1"
        :loading="loadingUsers"
      />
      <UButton
        :disabled="!selectedUserIds.length || adding"
        :loading="adding"
        size="sm"
        @click="handleAdd"
      >
        添加
      </UButton>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Participant {
  id: number;
  username: string;
}

interface UserOption {
  id: number;
  username: string;
}

const props = defineProps<{
  participants: Participant[];
  ownerId: number;
  canManage: boolean;
  onAdd: (userIds: number[]) => Promise<void>;
  onRemove: (userId: number) => Promise<void>;
}>();

const { apiRequest } = useApi();

// Nuxt UI v4 中 value-key 会使 v-model 存储 key 的值（number），所以用 number[] 类型
const selectedUserIds = ref<number[]>([]);
const adding = ref(false);
const loadingUsers = ref(false);
const allUsers = ref<UserOption[]>([]);

const currentParticipants = computed(() => props.participants);

const participantIds = computed(() => new Set(props.participants.map((p) => p.id)));

const availableUsers = computed(() =>
  allUsers.value.filter(
    (u) => u.id !== props.ownerId && !participantIds.value.has(u.id),
  ),
);

async function loadUsers() {
  loadingUsers.value = true;
  try {
    const res = await apiRequest<{ items: UserOption[] }>("/users/?page_size=200");
    allUsers.value = res.items || [];
  } catch {
    // ignore
  } finally {
    loadingUsers.value = false;
  }
}

async function handleAdd() {
  if (!selectedUserIds.value.length) return;
  adding.value = true;
  try {
    await props.onAdd(selectedUserIds.value);
    selectedUserIds.value = [];
  } finally {
    adding.value = false;
  }
}

async function handleRemove(userId: number) {
  await props.onRemove(userId);
}

onMounted(() => {
  if (props.canManage) {
    loadUsers();
  }
});
</script>
