import type { components } from "./api-types";
import { clearSession, session } from "./stores";

/**
 * 唯一出海口（HLD §5.1、SRS §6）：所有后端调用经此文件，类型全部来自后端
 * OpenAPI 生成的 api-types.ts（禁止手写 schema）。
 *   - token 注入：有会话即带 `Authorization: Bearer <token>`（SRS FR-2.3）；
 *   - 401 统一处理：清会话 + 回调路由层跳登录页（SRS FR-2.2）；
 *   - 错误归一：统一错误体 {"detail": ...}（HLD §9.2）→ ApiError(status, 中文消息)；
 *     网络层失败归一为 status 0。
 */

export type HealthResponse = components["schemas"]["HealthResponse"];
export type Credentials = components["schemas"]["Credentials"];
export type TokenResponse = components["schemas"]["TokenResponse"];
export type UserPublic = components["schemas"]["UserPublic"];

// 业务契约（D13：全部取自生成物，本文件不新写任何形状）
export type CalendarAggregate = components["schemas"]["CalendarAggregate"];
export type CalendarWeek = components["schemas"]["CalendarWeek"];
export type CalendarCell = components["schemas"]["CalendarCell"];
export type BodyMetricOut = components["schemas"]["BodyMetricOut"];
export type BodyMetricUpdate = components["schemas"]["BodyMetricUpdate"];
export type DayAggregate = components["schemas"]["DayAggregate"];
export type PlannedItemOut = components["schemas"]["PlannedItemOut"];
export type ActualItemOut = components["schemas"]["ActualItemOut"];
export type PlanItemCreate = components["schemas"]["PlanItemCreate"];
export type PlanItemMove = components["schemas"]["PlanItemMove"];
export type ActualItemCreate = components["schemas"]["ActualItemCreate"];
export type ActualItemUpdate = components["schemas"]["ActualItemUpdate"];
export type DayNoteUpdate = components["schemas"]["DayNoteUpdate"];
export type TemplateAggregate = components["schemas"]["TemplateAggregate"];
export type TemplateCreate = components["schemas"]["TemplateCreate"];
export type TemplateApplyRequest = components["schemas"]["TemplateApplyRequest"];
export type TemplateApplyResult = components["schemas"]["TemplateApplyResult"];

const API_BASE: string = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

interface RequestOptions {
  method?: HttpMethod;
  body?: unknown;
}

/** 401 后的跳转由路由层注册，避免 api.ts → router.ts → views → api.ts 的循环依赖。 */
let onUnauthorized: () => void = () => undefined;

export function setOnUnauthorized(handler: () => void): void {
  onUnauthorized = handler;
}

/** 错误体归一：字符串 detail 直取；422 为 Pydantic 原生数组，拼成中文分号串。 */
function extractDetail(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null || !("detail" in payload)) return null;
  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item: unknown) => {
        if (typeof item === "object" && item !== null && "msg" in item) return String(item.msg);
        return null;
      })
      .filter((msg): msg is string => msg !== null);
    return messages.length > 0 ? messages.join("；") : null;
  }
  return null;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (session.token !== null) headers.Authorization = `Bearer ${session.token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method ?? "GET",
      headers,
      ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
    });
  } catch {
    throw new ApiError(0, "网络异常，后端不可达");
  }

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    if (response.status === 401) {
      // token 被判无效/过期：先清会话再跳登录。登录端点自身的 401（密码错误）也走这里，
      // 此时已在 /login，路由层注册的回调会去重，仅把错误消息抛给当前页面展示。
      clearSession();
      onUnauthorized();
    }
    throw new ApiError(
      response.status,
      extractDetail(payload) ?? `${response.status} ${response.statusText}`,
    );
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

/** 注册即登录（SRS FR-1.4）：返回 token + user，写会话由调用方负责。 */
export function register(credentials: Credentials): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/register", { method: "POST", body: credentials });
}

/** 登录（SRS FR-2.1）；密码错误统一 401「用户名或密码不对」，由调用方展示。 */
export function login(credentials: Credentials): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", { method: "POST", body: credentials });
}

/**
 * 业务端点包装（SRS FR-4~FR-10）。约定（HLD §9.1）：
 *   - 路径不带 `API_BASE`（`request` 统一拼）；
 *   - 日级写操作的响应体**就是**新的日聚合 → 调用方整体替换本地快照，不再发二次 GET（D7）；
 *   - 只有 `PUT /metrics/{week_start}` 返回单行 metric（写体重只影响一格）。
 */

/** 参数编码：路径里的日期与月份都是 `YYYY-MM-DD` / `YYYY-MM`，直接 encode 兜底。 */
function seg(value: string): string {
  return encodeURIComponent(value);
}

/** 月历聚合（FR-4）：`month` 缺省 = 当月；`?month` 非法时后端静默回退，故以响应里的 year/month 为准。 */
export function getCalendar(month?: string): Promise<CalendarAggregate> {
  const query = month === undefined || month === "" ? "" : `?month=${seg(month)}`;
  return request<CalendarAggregate>(`/calendar${query}`);
}

/** 日聚合（FR-5）：无记录的日期返回空结构，不落库。 */
export function getDay(date: string): Promise<DayAggregate> {
  return request<DayAggregate>(`/days/${seg(date)}`);
}

/** 添加计划条目（FR-6.1）。 */
export function addPlanItem(date: string, body: PlanItemCreate): Promise<DayAggregate> {
  return request<DayAggregate>(`/days/${seg(date)}/plan-items`, { method: "POST", body });
}

/** 删除计划条目（FR-6.2）；已记录的实际条目只断开关联、不随之删除。 */
export function deletePlanItem(id: number): Promise<DayAggregate> {
  return request<DayAggregate>(`/plan-items/${id}`, { method: "DELETE" });
}

/** 上移 / 下移计划条目（FR-6.3）；边界上静默成功。 */
export function movePlanItem(id: number, body: PlanItemMove): Promise<DayAggregate> {
  return request<DayAggregate>(`/plan-items/${id}/move`, { method: "POST", body });
}

/** 按计划预填实际条目（FR-7.1）：幂等，无请求体。 */
export function prefillActualItems(date: string): Promise<DayAggregate> {
  return request<DayAggregate>(`/days/${seg(date)}/actual/prefill`, { method: "POST" });
}

/** 新增计划外实际条目（FR-7.3）。 */
export function addActualItem(date: string, body: ActualItemCreate): Promise<DayAggregate> {
  return request<DayAggregate>(`/days/${seg(date)}/actual-items`, { method: "POST", body });
}

/** 行内更新实际条目（FR-7.2）：三态语义 —— 字段缺省不动、`null` / 空串置空。 */
export function updateActualItem(id: number, body: ActualItemUpdate): Promise<DayAggregate> {
  return request<DayAggregate>(`/actual-items/${id}`, { method: "PATCH", body });
}

/** 删除实际条目（FR-7.4）。 */
export function deleteActualItem(id: number): Promise<DayAggregate> {
  return request<DayAggregate>(`/actual-items/${id}`, { method: "DELETE" });
}

/** 整段保存感受（FR-8.1）：空串合法 = 清空。 */
export function saveDayNote(date: string, body: DayNoteUpdate): Promise<DayAggregate> {
  return request<DayAggregate>(`/days/${seg(date)}/note`, { method: "PUT", body });
}

/** 模板列表（FR-9.1）。 */
export function listTemplates(): Promise<TemplateAggregate[]> {
  return request<TemplateAggregate[]>("/templates");
}

/** 新建模板（FR-9.2）：名称/天数按原始文本提交，服务端补「未命名循环」/回退 8 / 截断 12。 */
export function createTemplate(body: TemplateCreate): Promise<TemplateAggregate> {
  return request<TemplateAggregate>("/templates", { method: "POST", body });
}

/** 删除模板（FR-9.4）：返回剩余列表。 */
export function deleteTemplate(id: number): Promise<TemplateAggregate[]> {
  return request<TemplateAggregate[]>(`/templates/${id}`, { method: "DELETE" });
}

/** 把模板铺到日历（FR-9.3）：已有计划日的日期跳过且不覆盖。 */
export function applyTemplate(
  id: number,
  body: TemplateApplyRequest,
): Promise<TemplateApplyResult> {
  return request<TemplateApplyResult>(`/templates/${id}/apply`, { method: "POST", body });
}

/**
 * 周体重 upsert（FR-10）。注意契约是**整体替换**：只传 `weight` 会把该周已有的
 * `body_fat` / `note` 静默写成 NULL，调用方必须把原值一并回传（spec 决策 23）。
 */
export function saveWeekMetric(weekStart: string, body: BodyMetricUpdate): Promise<BodyMetricOut> {
  return request<BodyMetricOut>(`/metrics/${seg(weekStart)}`, { method: "PUT", body });
}
