<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import {
  addPlanItem,
  ApiError,
  deletePlanItem,
  getDay,
  movePlanItem,
  type DayAggregate,
  type PlanItemMove,
} from "../api";
import { dayTitle, dose } from "../format";

/**
 * 日详情（spec 决策 12–20、SRS FR-5/6）：日聚合的唯一持有者。
 *   - 按 date 挂载即拉取；视图用 `:key="date"` 保证换天即重建实例（决策 13）。
 *   - 一切写操作的响应体就是新的日聚合 → 整体替换本地快照，不发二次 GET、不做乐观更新（D7）。
 *   - 错误集中在详情顶部一处（决策 19）：404 提示「这条已经不存在了」并重拉当天，其它 4xx 只提示。
 *   - 竞态守卫（决策 20）：实例记住自己的日期，响应到达时日期已变则丢弃。
 * 本票先落计划列（增/删/移）与只读实际列；实际列交互在票 19。
 */

const props = defineProps<{ date: string }>();

const aggregate = ref<DayAggregate | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
/** 计划列操作进行中（增/删/移共用一把锁串行；v1 整段替换天然串行，此处同取向）。 */
const planPending = ref(false);

/** 实例对应的日期（决策 20 的守卫基准）。 */
const myDate = props.date;

const plannedItems = computed(() => aggregate.value?.planned_items ?? []);
const actualItems = computed(() => aggregate.value?.actual_items ?? []);

const form = reactive({ exercise: "", weight: "", sets: "", reps: "" });

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const next = await getDay(props.date);
    if (myDate !== props.date) return;
    aggregate.value = next;
  } catch (cause) {
    if (myDate !== props.date) return;
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    if (myDate === props.date) loading.value = false;
  }
}

/** 计划列写操作统一出口：禁用控件 → 等响应 → 整体替换聚合；404 重拉当天。 */
async function runPlanOp(op: () => Promise<DayAggregate>): Promise<boolean> {
  if (planPending.value) return false;
  planPending.value = true;
  error.value = null;
  try {
    const next = await op();
    if (myDate !== props.date) return false;
    aggregate.value = next;
    return true;
  } catch (cause) {
    if (myDate !== props.date) return false;
    if (cause instanceof ApiError && cause.status === 404) {
      // 条目已被别处删除：提示 + 重拉当日聚合（决策 19），界面不停在脏状态
      error.value = "这条已经不存在了";
      await refresh();
    } else {
      error.value = cause instanceof Error ? cause.message : String(cause);
    }
    return false;
  } finally {
    planPending.value = false;
  }
}

/** 新增计划条目（FR-6.1）：四字段按原始文本提交，服务端负责容错解析。 */
async function addItem(): Promise<void> {
  const ok = await runPlanOp(() =>
    addPlanItem(props.date, {
      exercise: form.exercise,
      weight: form.weight,
      sets: form.sets,
      reps: form.reps,
    }),
  );
  if (ok) {
    form.exercise = "";
    form.weight = "";
    form.sets = "";
    form.reps = "";
  }
}

function move(itemId: number, direction: PlanItemMove["direction"]): void {
  void runPlanOp(() => movePlanItem(itemId, { direction }));
}

function removeItem(itemId: number): void {
  void runPlanOp(() => deletePlanItem(itemId));
}

onMounted(refresh);
</script>

<template>
  <div class="day-detail-inner">
    <div class="day-detail-head">
      <h2>
        {{ dayTitle(date) }}<template v-if="aggregate?.title"> · {{ aggregate.title }}</template>
      </h2>
      <span v-if="aggregate?.kind === 'rest'" class="muted">休息日</span>
    </div>

    <!-- 错误集中在详情顶部一处（决策 19） -->
    <div v-if="error" class="flash error">{{ error }}</div>
    <p v-if="loading && aggregate === null" class="empty">正在加载…</p>

    <div v-if="aggregate !== null" class="cols">
      <section class="col-planned">
        <p class="col-title">计划</p>
        <ul v-if="plannedItems.length > 0" class="items">
          <li v-for="item in plannedItems" :key="item.id">
            <span class="name">{{ item.exercise }}</span>
            <span class="numbers">{{ dose(item.weight_kg, item.sets, item.reps) }}</span>
            <span class="actions">
              <button
                type="button"
                class="link"
                title="上移"
                :disabled="planPending"
                @click="move(item.id, 'up')"
              >
                ↑
              </button>
              <button
                type="button"
                class="link"
                title="下移"
                :disabled="planPending"
                @click="move(item.id, 'down')"
              >
                ↓
              </button>
              <button
                type="button"
                class="link"
                title="删除"
                :disabled="planPending"
                @click="removeItem(item.id)"
              >
                删
              </button>
            </span>
          </li>
        </ul>
        <p v-else class="empty">还没安排</p>
        <form class="inline" @submit.prevent="addItem">
          <input
            v-model="form.exercise"
            class="w-name"
            type="text"
            placeholder="动作"
            aria-label="动作"
          />
          <input
            v-model="form.weight"
            class="w-num"
            type="text"
            placeholder="重量"
            aria-label="重量"
          />
          <input
            v-model="form.sets"
            class="w-num"
            type="text"
            placeholder="组数"
            aria-label="组数"
          />
          <input
            v-model="form.reps"
            class="w-num"
            type="text"
            placeholder="次数"
            aria-label="次数"
          />
          <button class="primary" type="submit" :disabled="planPending">添加</button>
        </form>
      </section>

      <section class="col-actual">
        <p class="col-title">实际完成</p>
        <!-- 只读列（本票）；失焦 autosave / 预填 / 计划外新增 / 删除在票 19 -->
        <ul v-if="actualItems.length > 0" class="items">
          <li v-for="item in actualItems" :key="item.id">
            <span class="name">{{ item.exercise }}</span>
            <span class="numbers">{{ dose(item.weight_kg, item.sets, item.reps) }}</span>
          </li>
        </ul>
        <p v-else class="empty">还没记录</p>
      </section>
    </div>
  </div>
</template>
