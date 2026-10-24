import { reactive } from "vue";

/**
 * 会话小状态：token/user，localStorage 同步（HLD §5.1/§7、SRS FR-2）。
 * 路由守卫与 api.ts 的 token 注入都从这里读，保证同源。
 */

// TODO(认证票)：/auth/login、/auth/register 进入契约后，把本类型替换为
// api-types.ts 生成的 user schema（D13：前端类型只从生成物取，不手写后端形状）。
export interface SessionUser {
  username: string;
}

const TOKEN_KEY = "training-log.token";
const USER_KEY = "training-log.user";

/** localStorage 容错读取：坏 JSON / 缺字段一律按无会话处理，绝不抛错。 */
function loadUser(): SessionUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || !("username" in parsed)) return null;
    return typeof parsed.username === "string" ? { username: parsed.username } : null;
  } catch {
    return null;
  }
}

export interface SessionState {
  token: string | null;
  user: SessionUser | null;
}

export const session = reactive<SessionState>({
  token: localStorage.getItem(TOKEN_KEY),
  user: loadUser(),
});

/** 登录/注册成功后写入（SRS FR-1.4：注册即登录）。 */
export function setSession(token: string, user: SessionUser): void {
  session.token = token;
  session.user = user;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

/** 登出 / 401 清会话（SRS FR-2.4：登出为纯前端行为，无服务端会话表）。 */
export function clearSession(): void {
  session.token = null;
  session.user = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isAuthenticated(): boolean {
  return session.token !== null;
}
