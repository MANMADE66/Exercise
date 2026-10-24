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
