<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import {
  addActualItem,
  addPlanItem,
  ApiError,
  deleteActualItem,
  deletePlanItem,
  getDay,
  movePlanItem,
  prefillActualItems,
  saveDayNote,
  updateActualItem,
  type ActualItemOut,
  type ActualItemUpdate,
  type DayAggregate,
  type PlanItemMove,
} from "../api";
import { dayTitle, dose, weightText } from "../format";

/**
 * 日详情（spec 决策 12–20、SRS FR-5~FR-8）：日聚合的唯一持有者。
 *   - 按 date 挂载即拉取；视图用 `:key="date"` 保证换天即重建实例（决策 13）。
 *   - 一切写操作的响应体就是新的日聚合 → 整体替换本地快照，不发二次 GET、不做乐观更新（D7）。
 *   - 实际条目 autosave **逐字段**（决策 15）：失焦只 PATCH 该字段，契约三态（缺省不动）保证
 *     「两秒内先后失焦两个字段，两个改动都保住」；绝不整行快照提交。
 *   - 错误集中在详情顶部一处（决策 19）：404 提示「这条已经不存在了」并重拉当天，其它 4xx 只提示。
 *   - 竞态守卫（决策 20）：实例记住自己的日期，响应到达时日期已变则丢弃；写操作最后完成者生效。
 */

const props = defineProps<{ date: string }>();

const aggregate = ref<DayAggregate | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

/** 计划列操作锁（增/删/移共用，v1 整段替换天然串行，同取向）。 */
const planPending = ref(false);
/** 预填 / 计划外新增 / 感受 各自的操作锁（决策 18：禁用触发控件，不做全局遮罩）。 */
const prefillPending = ref(false);
const addPending = ref(false);
const notePending = ref(false);
/** 正在删除的实际条目 id（行级锁）。 */
const rowDeleting = reactive(new Set<number>());

/** 实例对应的日期（决策 20 的守卫基准）。 */
const myDate = props.date;

const plannedItems = computed(() => aggregate.value?.planned_items ?? []);
const actualItems = computed(() => aggregate.value?.actual_items ?? []);

const form = reactive({ exercise: "", weight: "", sets: "", reps: "" });
const actualForm = reactive({ exercise: "", weight: "", sets: "", reps: "" });

// ---------- 实际条目草稿（逐字段 autosave 的本地态） ----------

type ActualField = "weight" | "sets" | "reps" | "note";

interface FieldDraft {
  /** 输入框当前文本。 */
  text: string;
  /** 服务端已接受（或在途）的文本：失焦时 text === saved 就不发请求。 */
  saved: string;
  /** 该字段的 PATCH 在途中。 */
  pending: boolean;
}

type RowDraft = Record<ActualField, FieldDraft>;

/** 每行实际条目的草稿；aggregate 替换时按「在途/正在输入的字段不回灌」规则同步。 */
const drafts = reactive(new Map<number, RowDraft>());
/** 正在聚焦输入的字段（`${itemId}:${field}`）；响应回来时不回灌，避免打掉正在敲的字。 */
const editingKey = ref<string | null>(null);

/** 从服务端条目构造草稿（显示值与 v1 一致：重量/组数取解析后的规范文本，次数/备注原文）。 */
function rowFromItem(item: ActualItemOut): RowDraft {
  const weight = weightText(item.weight_kg);
  const sets = item.sets === null || item.sets === undefined ? "" : String(item.sets);
  const reps = item.reps ?? "";
  const note = item.note ?? "";
  const field = (text: string): FieldDraft => ({ text, saved: text, pending: false });
  return { weight: field(weight), sets: field(sets), reps: field(reps), note: field(note) };
}

/** 用新聚合同步草稿：新行补草稿，删掉的行丢草稿，在途/聚焦字段保持用户文本。 */
function syncDrafts(day: DayAggregate): void {
  const seen = new Set<number>();
  for (const item of day.actual_items ?? []) {
    seen.add(item.id);
    const existing = drafts.get(item.id);
    if (existing === undefined) {
      drafts.set(item.id, rowFromItem(item));
      continue;
    }
    const fresh = rowFromItem(item);
    (["weight", "sets", "reps", "note"] as const).forEach((name) => {
      const target = existing[name];
      if (target.pending) return;
      if (editingKey.value === `${item.id}:${name}`) return;
      target.text = fresh[name].text;
      target.saved = fresh[name].saved;
    });
  }
  // Map 迭代器是实时的，遍历时删除安全
  for (const id of drafts.keys()) {
    if (!seen.has(id)) drafts.delete(id);
  }
}

const actualRows = computed(() =>
  actualItems.value.flatMap((item) => {
    const draft = drafts.get(item.id);
    return draft === undefined ? [] : [{ item, draft }];
  }),
);

// ---------- 感受 ----------

const noteText = ref("");
/** 正在写感受：聚合替换时不回灌文本域。 */
const noteEditing = ref(false);

// ---------- 聚合读写 ----------

function applyAggregate(next: DayAggregate): void {
  aggregate.value = next;
  syncDrafts(next);
  if (!noteEditing.value) noteText.value = next.note;
}

async function refresh(): Promise<boolean> {
  loading.value = true;
  try {
    const next = await getDay(props.date);
    if (myDate !== props.date) return false;
    applyAggregate(next);
    error.value = null;
    return true;
  } catch (cause) {
    if (myDate !== props.date) return false;
    error.value = cause instanceof Error ? cause.message : String(cause);
    return false;
  } finally {
    if (myDate === props.date) loading.value = false;
  }
}

/**
 * 写操作统一出口：等响应 → 整体替换聚合；404 重拉当天（重拉成功才补「已经不存在了」，
 * 避免 refresh 开头清错误把提示抹掉）。不加锁 —— 锁在各操作入口。
 */
async function execute(op: () => Promise<DayAggregate>): Promise<DayAggregate | null> {
  error.value = null;
  try {
    const next = await op();
    if (myDate !== props.date) return null;
    applyAggregate(next);
    return next;
  } catch (cause) {
    if (myDate !== props.date) return null;
    if (cause instanceof ApiError && cause.status === 404) {
      const ok = await refresh();
      if (ok) error.value = "这条已经不存在了";
    } else {
      error.value = cause instanceof Error ? cause.message : String(cause);
    }
    return null;
  }
}

// ---------- 计划列 ----------

async function runPlanOp(op: () => Promise<DayAggregate>): Promise<boolean> {
  if (planPending.value) return false;
  planPending.value = true;
  const result = await execute(op);
  planPending.value = false;
  return result !== null;
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

// ---------- 实际列：逐字段 autosave ----------

function focusField(itemId: number, field: ActualField): void {
  editingKey.value = `${itemId}:${field}`;
}

function blurField(itemId: number, field: ActualField): void {
  if (editingKey.value === `${itemId}:${field}`) editingKey.value = null;
  void saveField(itemId, field);
}

/**
 * 失焦保存一个字段（FR-7.2）：只 PATCH 该字段，空串 = 置空（契约三态）。
 * `saved` 先推进作「在途不重发」的闸；失败回退基准，下次失焦可重试。
 */
async function saveField(itemId: number, field: ActualField): Promise<void> {
  const row = drafts.get(itemId);
  if (row === undefined) return;
  const target = row[field];
  if (target.pending || target.text === target.saved) return;
  const previous = target.saved;
  target.saved = target.text;
  target.pending = true;
  const body: ActualItemUpdate = {};
  body[field] = target.text;
  const result = await execute(() => updateActualItem(itemId, body));
  if (result === null) {
    target.saved = previous;
  } else {
    // 回显服务端的规范文本（v1 同：「60kg」保存后显示「60」）；syncDrafts 因在途跳过了本字段
    const item = (result.actual_items ?? []).find((it) => it.id === itemId);
    if (item !== undefined) {
      const fresh = rowFromItem(item)[field];
      target.text = fresh.text;
      target.saved = fresh.saved;
    }
  }
  target.pending = false;
}

/** 按计划预填（FR-7.1）：幂等；按钮仅在当天有计划条目时渲染（决策 17）。 */
async function prefill(): Promise<void> {
  if (prefillPending.value) return;
  prefillPending.value = true;
  await execute(() => prefillActualItems(props.date));
  prefillPending.value = false;
}

/** 计划外新增（FR-7.3）：隐式建日由服务端处理；成功后清表单。 */
async function addActual(): Promise<void> {
  if (addPending.value) return;
  addPending.value = true;
  const ok = await execute(() =>
    addActualItem(props.date, {
      exercise: actualForm.exercise,
      weight: actualForm.weight,
      sets: actualForm.sets,
      reps: actualForm.reps,
    }),
  );
  if (ok !== null) {
    actualForm.exercise = "";
    actualForm.weight = "";
    actualForm.sets = "";
    actualForm.reps = "";
  }
  addPending.value = false;
}

function removeActual(itemId: number): void {
  if (rowDeleting.has(itemId)) return;
  rowDeleting.add(itemId);
  void execute(() => deleteActualItem(itemId)).finally(() => {
    rowDeleting.delete(itemId);
  });
}

/** 感受整段保存（FR-8.1）：显式按钮（v1 同），空串 = 清空；保存后详情不收起。 */
async function saveNote(): Promise<void> {
  if (notePending.value) return;
  notePending.value = true;
  const ok = await execute(() => saveDayNote(props.date, { text: noteText.value }));
  if (ok !== null) noteText.value = ok.note;
  notePending.value = false;
}

onMounted(() => {
  void refresh();
});
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
        <ul v-if="actualRows.length > 0" class="items">
          <li v-for="row in actualRows" :key="row.item.id">
            <div class="row-form">
              <span class="name">{{ row.item.exercise }}</span>
              <input
                v-model="row.draft.weight.text"
                class="w-num"
                type="text"
                aria-label="重量"
                :disabled="row.draft.weight.pending"
                @focus="focusField(row.item.id, 'weight')"
                @blur="blurField(row.item.id, 'weight')"
              />
              <input
                v-model="row.draft.sets.text"
                class="w-num"
                type="text"
                aria-label="组数"
                :disabled="row.draft.sets.pending"
                @focus="focusField(row.item.id, 'sets')"
                @blur="blurField(row.item.id, 'sets')"
              />
              <input
                v-model="row.draft.reps.text"
                class="w-mid"
                type="text"
                aria-label="次数"
                :disabled="row.draft.reps.pending"
                @focus="focusField(row.item.id, 'reps')"
                @blur="blurField(row.item.id, 'reps')"
              />
              <input
                v-model="row.draft.note.text"
                class="w-note"
                type="text"
                placeholder="备注"
                aria-label="备注"
                :disabled="row.draft.note.pending"
                @focus="focusField(row.item.id, 'note')"
                @blur="blurField(row.item.id, 'note')"
              />
              <button
                type="button"
                class="link"
                title="删除"
                :disabled="rowDeleting.has(row.item.id)"
                @click="removeActual(row.item.id)"
              >
                删
              </button>
            </div>
          </li>
        </ul>
        <p v-else class="empty">还没记录</p>
        <form v-if="plannedItems.length > 0" class="inline" @submit.prevent="prefill">
          <button type="submit" :disabled="prefillPending">按计划预填</button>
        </form>
        <form class="inline" @submit.prevent="addActual">
          <input
            v-model="actualForm.exercise"
            class="w-name"
            type="text"
            placeholder="计划外的动作"
            aria-label="计划外的动作"
          />
          <input
            v-model="actualForm.weight"
            class="w-num"
            type="text"
            placeholder="重量"
            aria-label="重量"
          />
          <input
            v-model="actualForm.sets"
            class="w-num"
            type="text"
            placeholder="组数"
            aria-label="组数"
          />
          <input
            v-model="actualForm.reps"
            class="w-num"
            type="text"
            placeholder="次数"
            aria-label="次数"
          />
          <button type="submit" :disabled="addPending">添加</button>
        </form>
      </section>
    </div>

    <div v-if="aggregate !== null" class="note-box">
      <p class="col-title">感受</p>
      <form @submit.prevent="saveNote">
        <textarea
          v-model="noteText"
          placeholder="今天练得怎么样？哪里不对、哪里顺，随便写两句。"
          aria-label="感受"
          @focus="noteEditing = true"
          @blur="noteEditing = false"
        ></textarea>
        <div class="inline-actions">
          <button type="submit" :disabled="notePending">保存</button>
        </div>
      </form>
    </div>
  </div>
</template>
