<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { getCalendar, type CalendarAggregate } from "../api";
import MonthGrid from "../components/MonthGrid.vue";
import { monthKey, shiftMonth, todayIso } from "../format";

/**
 * 月历视图：月历聚合的唯一持有者（spec 决策 3），展开日期也在这里（决策 12）。
 * 本票只做只读网格；票 17 往第 8 列填 WeekMetric，票 18 往 MonthGrid 的 `expanded` 插槽里放 DayDetail。
 */

const aggregate = ref<CalendarAggregate | null>(null);
const error = ref<string | null>(null);
const loading = ref(false);
/** 展开的日期；只影响格子的 is-selected 高亮，切月清空（票 18 才有展开内容）。 */
const expandedDate = ref<string | null>(null);
/** 请求的月份 `YYYY-MM`；null = 不带 `?month`，由后端按「当月」处理。 */
const requestedMonth = ref<string | null>(null);

/** 竞态守卫：快速翻月时只认最后一次请求的响应（与决策 20 同一取向）。 */
let requestSeq = 0;

/** 契约不带 today（决策 11）：本地日期只用于视觉标记。 */
const today = todayIso();

/** 标题取响应里**生效**的 year/month（决策 11、AC：`?month` 非法时后端静默回退）。 */
const title = computed<string>(() => {
  const data = aggregate.value;
  return data === null ? "月历" : `${data.year} 年 ${data.month} 月`;
});

/** 渲染循环里做 includes 是 O(n²)（决策 9），先转成 Set 再传。 */
const loggedDates = computed<Set<string>>(
  () => new Set<string>(aggregate.value?.logged_dates ?? []),
);

async function load(): Promise<void> {
  requestSeq += 1;
  const seq = requestSeq;
  loading.value = true;
  error.value = null;
  try {
    const data = await getCalendar(requestedMonth.value ?? undefined);
    if (seq !== requestSeq) return;
    aggregate.value = data;
  } catch (cause) {
    if (seq !== requestSeq) return;
    // api.ts 已把错误体归一为中文消息；这里不判 401（401 由 api.ts 清会话并跳登录）
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    if (seq === requestSeq) loading.value = false;
  }
}

/** 翻月：以响应里的 year/month 为基准算 `YYYY-MM`（决策 11、FR-4.4）。 */
function go(delta: number): void {
  const data = aggregate.value;
  if (data === null) return;
  const next = shiftMonth(data.year, data.month, delta);
  requestedMonth.value = monthKey(next.year, next.month);
  expandedDate.value = null;
  void load();
}

/** 点同一格收起、点另一天换天（决策 12）。 */
function select(date: string): void {
  expandedDate.value = expandedDate.value === date ? null : date;
}

onMounted(() => {
  void load();
});
</script>

<template>
  <div class="topbar">
    <h1>{{ title }}</h1>
    <nav class="nav">
      <button
        type="button"
        class="nav-step"
        :disabled="loading || aggregate === null"
        @click="go(-1)"
      >
        上个月
      </button>
      <button
        type="button"
        class="nav-step"
        :disabled="loading || aggregate === null"
        @click="go(1)"
      >
        下个月
      </button>
    </nav>
  </div>
  <p class="sub">点某一天，看当天的计划与实际完成。</p>

  <!-- 请求失败：页面顶部一句中文错误 + 重试，不白屏（AC） -->
  <div v-if="error" class="flash error">
    {{ error }}
    <button type="button" :disabled="loading" @click="load">重试</button>
  </div>

  <p v-if="loading && aggregate === null" class="empty">正在加载月历…</p>

  <MonthGrid
    v-if="aggregate !== null"
    :weeks="aggregate.weeks"
    :selected-date="expandedDate"
    :today="today"
    :logged-dates="loggedDates"
    @select="select"
  >
    <!-- 票 18 在此放 <template #expanded><DayDetail :date="expandedDate" /></template>；
         本票不提供插槽内容，MonthGrid 就不会渲染那行 colspan 展开行。 -->
  </MonthGrid>
</template>
