import { createRouter, createWebHistory } from "vue-router";

import { setOnUnauthorized } from "./api";
import { isAuthenticated } from "./stores";
import CalendarView from "./views/CalendarView.vue";
import LoginView from "./views/LoginView.vue";
import TemplatesView from "./views/TemplatesView.vue";

declare module "vue-router" {
  interface RouteMeta {
    /** true = 无需会话即可访问（仅 /login）。 */
    public?: boolean;
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: { name: "calendar" } },
    { path: "/login", name: "login", component: LoginView, meta: { public: true } },
    { path: "/calendar", name: "calendar", component: CalendarView },
    { path: "/templates", name: "templates", component: TemplatesView },
    { path: "/:pathMatch(.*)*", redirect: { name: "calendar" } },
  ],
});

// 全局守卫（SRS §6）：无 token 一律重定向 /login；已登录访问 /login 则回月历。
router.beforeEach((to) => {
  if (to.meta.public === true) {
    return isAuthenticated() ? { name: "calendar" } : true;
  }
  return isAuthenticated() ? true : { name: "login" };
});

// 401 统一出口（SRS FR-2.2）：api.ts 清会话后回调这里跳登录页；已在登录页则不重复跳转。
setOnUnauthorized(() => {
  if (router.currentRoute.value.name !== "login") {
    void router.replace({ name: "login" });
  }
});
