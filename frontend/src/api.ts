import type { components } from "./api-types";

/**
 * 唯一出海口：类型全部来自后端 OpenAPI 生成的 api-types.ts（禁止手写 schema）。
 * token 注入与 401 统一跳登录在认证票落地时补入本文件。
 */

export type HealthResponse = components["schemas"]["HealthResponse"];

const API_BASE: string = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...init.headers },
  });
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}
