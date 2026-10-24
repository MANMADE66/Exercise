/**
 * 纯函数模块（无 DOM 依赖）：v1 Jinja 过滤器 `weight_text` / `format_dose` 与月历翻页的等价物。
 *
 * 这些格式化只此一份 —— 组件里不许各自重写（票 16 验收）。将来若要给前端加测试运行器，
 * 本文件是唯一的落点（spec 决策 38：本轮不引入 runner，只预留纯度最高的这层）。
 */

const pad2 = (value: number): string => String(value).padStart(2, "0");

/**
 * 重量文本：无多余小数、去尾零；空值 → 空串（v1 `f"{value:g}"` 的等价物）。
 *
 * `toFixed(3)` 先消掉浮点噪声（`0.1 + 0.2` 之类的尾巴），再删掉末尾的零与孤立小数点。
 */
export function weightText(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "";
  return value.toFixed(3).replace(/\.?0+$/, "");
}

/**
 * 剂量文本：「重量 kg · N 组 · 次数」用 `·` 拼接，空值一律跳过（绝不出现 `None` / `NaN`）。
 *
 * 与 v1 `format_dose` 同义：重量为 null 不加 `kg` 段；次数为空串或 null 不加次数段。
 */
export function dose(
  weight: number | null | undefined,
  sets: number | null | undefined,
  reps: string | null | undefined,
): string {
  const parts: string[] = [];
  const weightValue = weightText(weight);
  if (weightValue !== "") parts.push(`${weightValue} kg`);
  if (sets !== null && sets !== undefined) parts.push(`${sets} 组`);
  if (reps !== null && reps !== undefined && reps !== "") parts.push(reps);
  return parts.join(" · ");
}

/**
 * 本地今天（`YYYY-MM-DD`）。契约不带 `today`（spec 决策 11），只影响视觉标记。
 * 不能拿 `toISOString()` 切 —— 那是 UTC，东八区的凌晨会偏成前一天。
 */
export function todayIso(now: Date = new Date()): string {
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
}

/** `YYYY-MM`：`?month=` 与翻月基准用；月份补零（v1 `f"{index // 12:04d}-{index % 12 + 1:02d}"`）。 */
export function monthKey(year: number, month: number): string {
  return `${year}-${pad2(month)}`;
}

/** 翻月：`delta` 为 ±1 时得到上/下个月，跨年自动进位（返回生效的 year/month）。 */
export function shiftMonth(
  year: number,
  month: number,
  delta: number,
): { year: number; month: number } {
  const index = year * 12 + (month - 1) + delta;
  const nextYear = Math.floor(index / 12);
  return { year: nextYear, month: index - nextYear * 12 + 1 };
}

/** 从 `YYYY-MM-DD` 取「几号」作为格子数字（去掉前导零，v1 显示的是 int）；认不出则空串。 */
export function dayOfMonth(isoDate: string): string {
  const day = Number(isoDate.slice(8, 10));
  return Number.isFinite(day) && day >= 1 ? String(day) : "";
}
