<script setup lang="ts">
import { useRouter } from "vue-router";

import { clearSession, session } from "../stores";

/**
 * 顶栏（HLD §4.1、spec 决策 7）：用户名 + 「月历 / 模板」导航（当前路由高亮）+ 登出。
 * 登出是纯前端行为（SRS FR-2.4：无服务端会话表），逻辑从 App.vue 下沉到这里。
 */

const router = useRouter();

function logout(): void {
  clearSession();
  void router.replace({ name: "login" });
}
</script>

<template>
  <header class="topbar">
    <div class="topbar-main">
      <span class="brand">训练记录</span>
      <nav v-if="session.token" class="nav">
        <RouterLink to="/calendar">月历</RouterLink>
        <RouterLink to="/templates">模板</RouterLink>
      </nav>
    </div>
    <div v-if="session.token" class="who">
      <span class="muted">{{ session.user?.username }}</span>
      <button type="button" @click="logout">登出</button>
    </div>
  </header>
</template>
