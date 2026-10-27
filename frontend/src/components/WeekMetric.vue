<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { ApiError, errorMessage, saveWeekMetric, type BodyMetricOut } from "../api";
import { weightText } from "../format";

/**
 * 周体重（SRS FR-10、spec 决策 21–24）：月历每行右侧一个输入框，失焦即存。
 *   - 该行 metric 归本组件自己持有（决策 3）；保存成功用响应就地替换，不重拉月历（决策 22）。
 *   - PUT 是**整体替换**（决策 23）：保存时必须把该行已有的体脂率/备注原值一并回传，
 *     否则会被静默写成 NULL（这两个字段本轮没有输入控件，v1 也没有）。
 *   - 非法体重是 422、结构性不落库：还原成上次保存值 + 行内提示（决策 24）。
 */

const props = defineProps<{
  weekStart: string;
  metric: BodyMetricOut | null;
}>();

/** 该行当前已保存的 metric（本组件是唯一持有者；父级换月重取时随 props 同步）。 */
const savedMetric = ref<BodyMetricOut | null>(props.metric);
const text = ref<string>(weightText(props.metric?.weight_kg));
const saving = ref(false);
const error = ref<string | null>(null);

watch(
  () => props.metric,
  (next) => {
    savedMetric.value = next;
    text.value = weightText(next?.weight_kg);
  },
);

/** 上次保存值的显示文本：非法输入还原到这里（也用作「没改就不发请求」的基准）。 */
const savedText = computed<string>(() => weightText(savedMetric.value?.weight_kg));

async function save(): Promise<void> {
  if (saving.value) return;
  const trimmed = text.value.trim();
  if (trimmed === savedText.value) return; // 没变就不写（含空框路过失焦）
  saving.value = true;
  error.value = null;
  try {
    const metric = savedMetric.value;
    const bodyFat = metric?.body_fat_pct;
    const result = await saveWeekMetric(props.weekStart, {
      weight: text.value,
      body_fat: bodyFat === null || bodyFat === undefined ? null : String(bodyFat),
      note: metric?.note ?? null,
    });
    savedMetric.value = result;
    text.value = savedText.value;
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 422) {
      text.value = savedText.value;
    }
    error.value = errorMessage(cause);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <input
    v-model="text"
    type="text"
    placeholder="kg"
    aria-label="本周体重"
    :disabled="saving"
    @blur="save"
  />
  <p v-if="error" class="error">{{ error }}</p>
</template>
