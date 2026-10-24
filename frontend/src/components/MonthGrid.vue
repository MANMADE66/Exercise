<script setup lang="ts">
import { computed } from "vue";

import type { CalendarWeek } from "../api";
import { dayOfMonth } from "../format";

/**
 * 月历的**表结构**（spec 决策 8/9）：表头 + 按周的行 + 格子状态类 + 展开行插槽。
 * 不持有任何日级状态 —— 展开日期与日聚合都在视图/详情组件里。
 *
 * 展开行只在这里写一次 `colspan="8"`：票 17 填第 8 列（周体重），票 18 往插槽里放 DayDetail，
 * 两票都不用碰列宽/跨列。
 */

const props = defineProps<{
  weeks: CalendarWeek[];
  selectedDate: string | null;
  today: string;
  loggedDates: Set<string>;
}>();

const emit = defineEmits<{ select: [date: string] }>();

/** 作用域插槽：内容由视图提供；没提供就一行都不渲染（不留空行边框）。 */
const slots = defineSlots<{ expanded?: () => unknown }>();

const weekdayLabels = ["一", "二", "三", "四", "五", "六", "日"];

/** 展开行落在选中日期所在的那一周之后；没有选中日期时为 -1（不渲染）。 */
const expandedRowIndex = computed<number>(() => {
  const selected = props.selectedDate;
  if (selected === null) return -1;
  return props.weeks.findIndex((week) =>
    week.cells.some((cell) => cell !== null && cell.date === selected),
  );
});

function select(date: string): void {
  emit("select", date);
}
</script>

<template>
  <table class="month">
    <thead>
      <tr>
        <th v-for="label in weekdayLabels" :key="label">{{ label }}</th>
        <th class="week-head">周体重</th>
      </tr>
    </thead>
    <tbody>
      <template v-for="(week, weekIndex) in weeks" :key="week.week_start">
        <tr>
          <template
            v-for="(cell, columnIndex) in week.cells"
            :key="`${week.week_start}-${columnIndex}`"
          >
            <!-- 补齐位（不在本月）：空白、不可点、不画「已记」圆点 -->
            <td v-if="cell === null" class="day-cell"></td>
            <td
              v-else
              class="day-cell"
              :class="{
                'is-rest': cell.kind === 'rest',
                'is-today': cell.date === today,
                'is-selected': cell.date === selectedDate,
                'has-log': loggedDates.has(cell.date),
              }"
              :data-date="cell.date"
              @click="select(cell.date)"
            >
              <div class="num">{{ dayOfMonth(cell.date) }}</div>
              <!-- 无标题的训练日不显示标签；休息日固定显示「休息」 -->
              <div v-if="cell.title || cell.kind === 'rest'" class="part">
                {{ cell.title || "休息" }}
              </div>
            </td>
          </template>
          <!-- 第 8 列：周体重（票 17 填 WeekMetric；本票先留空单元格以对齐表头） -->
          <td class="week-cell"></td>
        </tr>
        <tr
          v-if="slots.expanded !== undefined && weekIndex === expandedRowIndex"
          class="day-detail"
        >
          <td colspan="8"><slot name="expanded" /></td>
        </tr>
      </template>
    </tbody>
  </table>
</template>
