<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import {
  applyTemplate,
  createTemplate,
  deleteTemplate,
  listTemplates,
  type TemplateAggregate,
  type TemplateApplyResult,
} from "../api";
import { todayIso } from "../format";

/**
 * 模板页（SRS FR-9、spec 决策 25–30）：模板列表的唯一持有者。
 *   - 名称与天数按**原始文本**提交（契约收文本，服务端负责回退 8 / 截断 12 / 空名补「未命名循环」），
 *     前端不自己先校验或截断，否则与服务端语义分叉。
 *   - 固定渲染 12 个日块（v1 的 max_days）；天数只决定服务端取前几个。
 *   - 新建/删除后重新拉 GET /templates（不在本地拼列表，与服务端排序保持一致的唯一来源）。
 *   - 铺排结果提示停在模板页（不自动跳月历）；月历每次进入都重新请求，不需要通知失效。
 *   - 删除是 FR-9.4 新开放的能力（级联删天与条目、不可撤销）→ 一次浏览器确认框（本轮唯一新增交互）。
 */

/** v1 的 max_days：新建表单固定 12 个日块。 */
const MAX_DAYS = 12;

const templates = ref<TemplateAggregate[]>([]);
const loaded = ref(false);
const loading = ref(false);
const error = ref<string | null>(null);

/** 最近一次铺排结果（计数 + 跳过日期列表；契约专门回传 skipped_dates）。 */
const applyResult = ref<TemplateApplyResult | null>(null);

const applying = reactive(new Set<number>());
const deleting = reactive(new Set<number>());
const creating = ref(false);

/** 每个模板一行的起始日期（默认今天）；跨刷新保留用户已改的值。 */
const starts = reactive<Record<number, string>>({});
const today = todayIso();

const name = ref("");
const lengthDays = ref("8");
const dayBlocks = reactive(
  Array.from({ length: MAX_DAYS }, () => ({ title: "", rest: false, items: "" })),
);

function startFor(id: number): string {
  return starts[id] ?? today;
}

function setStart(id: number, event: Event): void {
  if (event.target instanceof HTMLInputElement) starts[id] = event.target.value;
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const list = await listTemplates();
    templates.value = list;
    const seen = new Set<number>();
    for (const t of list) {
      seen.add(t.id);
      starts[t.id] = starts[t.id] ?? today;
    }
    for (const key of Object.keys(starts)) {
      const id = Number(key);
      if (!seen.has(id)) delete starts[id];
    }
    loaded.value = true;
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    loading.value = false;
  }
}

/** 铺到日历（FR-9.3）：绝不覆盖已有计划日；结果（含跳过日期）显示在本页顶部。 */
async function apply(templateId: number): Promise<void> {
  if (applying.has(templateId)) return;
  applying.add(templateId);
  error.value = null;
  applyResult.value = null;
  try {
    applyResult.value = await applyTemplate(templateId, { start: startFor(templateId) });
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    applying.delete(templateId);
  }
}

/** 删除模板（FR-9.4）：确认一次；成功用 GET /templates 重拉列表。 */
async function removeTemplate(templateId: number, templateName: string): Promise<void> {
  if (deleting.has(templateId)) return;
  if (!window.confirm(`删除模板「${templateName}」？它的天和动作会一起删掉，撤不回来。`)) return;
  deleting.add(templateId);
  error.value = null;
  applyResult.value = null;
  try {
    await deleteTemplate(templateId);
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    deleting.delete(templateId);
  }
}

/** 新建模板（FR-9.2）：名称/天数/标题原始文本提交；动作一行一个、空行忽略；成功后重拉列表。 */
async function create(): Promise<void> {
  if (creating.value) return;
  creating.value = true;
  error.value = null;
  applyResult.value = null;
  try {
    await createTemplate({
      name: name.value,
      length_days: lengthDays.value,
      days: dayBlocks.map((block) => ({
        kind: block.rest ? "rest" : "train",
        title: block.title,
        items: block.items
          .split("\n")
          .filter((line) => line.trim() !== "")
          .map((line) => ({ exercise: line })),
      })),
    });
    name.value = "";
    lengthDays.value = "8";
    for (const block of dayBlocks) {
      block.title = "";
      block.rest = false;
      block.items = "";
    }
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    creating.value = false;
  }
}

onMounted(() => {
  void load();
});
</script>

<template>
  <div class="topbar">
    <h1>循环模板</h1>
  </div>
  <p class="sub">
    把一套循环存成模板，之后选个起始日期一键铺到日历上。已经排过的日期会跳过，不会覆盖你已经写好的内容。
  </p>

  <!-- 错误与铺排结果都在页面顶部（决策 28/30） -->
  <div v-if="error" class="flash error">{{ error }}</div>
  <div v-if="applyResult !== null" class="flash">
    <div>新建 {{ applyResult.created }} 天，跳过 {{ applyResult.skipped }} 天</div>
    <div v-if="(applyResult.skipped_dates ?? []).length > 0">
      跳过的日期：{{ applyResult.skipped_dates?.join("、") }}
    </div>
  </div>

  <p v-if="!loaded && loading" class="empty">正在加载…</p>
  <div v-if="templates.length > 0" class="card">
    <h3>已有的模板</h3>
    <ul class="tpl-list">
      <li v-for="t in templates" :key="t.id">
        <span>{{ t.name }} · {{ t.length_days }} 天</span>
        <form class="inline" @submit.prevent="apply(t.id)">
          <input
            type="date"
            :value="startFor(t.id)"
            aria-label="起始日期"
            @input="setStart(t.id, $event)"
          />
          <button type="submit" :disabled="applying.has(t.id)">铺到日历</button>
          <button
            type="button"
            class="link"
            title="删除"
            :disabled="deleting.has(t.id)"
            @click="removeTemplate(t.id, t.name)"
          >
            删除
          </button>
        </form>
      </li>
    </ul>
  </div>
  <p v-else-if="loaded && error === null" class="empty">还没有模板，先在下面建一套循环。</p>

  <div class="card">
    <h3>新建模板</h3>
    <form @submit.prevent="create">
      <div class="inline">
        <input
          v-model="name"
          class="w-name"
          type="text"
          placeholder="模板名，例如 八天循环"
          aria-label="模板名"
        />
        <input v-model="lengthDays" class="w-num" type="text" aria-label="循环天数" />
        <span class="muted">天</span>
        <button class="primary" type="submit" :disabled="creating">保存模板</button>
      </div>
      <p class="muted" style="margin-top: 10px">
        天数填几就只用前几天的内容。每天填部位名、勾不勾休息、动作一行一个；重量不写进模板，铺出来之后按天填。
      </p>

      <div v-for="(block, i) in dayBlocks" :key="i" class="tpl-day">
        <div class="inline">
          <span class="muted w-day">第 {{ i + 1 }} 天</span>
          <input
            v-model="block.title"
            class="w-name"
            type="text"
            placeholder="部位，例如 胸 + 二头"
            :aria-label="`第 ${i + 1} 天部位`"
          />
          <label class="muted"><input v-model="block.rest" type="checkbox" /> 休息</label>
        </div>
        <textarea
          v-model="block.items"
          rows="2"
          placeholder="动作，一行一个"
          :aria-label="`第 ${i + 1} 天动作`"
        ></textarea>
      </div>
    </form>
  </div>
</template>
