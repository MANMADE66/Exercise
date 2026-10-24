<script setup lang="ts">
import { useRouter } from "vue-router";

import { clearSession, session } from "./stores";

const router = useRouter();

function logout(): void {
  // SRS FR-2.4：登出为纯前端行为——清本地 token 并跳登录页。
  clearSession();
  void router.replace({ name: "login" });
}
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <strong>训练记录 v2</strong>
      <span class="badge">骨架</span>
      <nav v-if="session.token" class="nav">
        <RouterLink to="/calendar">月历</RouterLink>
        <RouterLink to="/templates">模板</RouterLink>
      </nav>
      <span class="spacer"></span>
      <template v-if="session.token">
        <span v-if="session.user" class="muted">{{ session.user.username }}</span>
        <button type="button" @click="logout">登出</button>
      </template>
    </header>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>
