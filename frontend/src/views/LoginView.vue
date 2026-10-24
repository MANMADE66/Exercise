<script setup lang="ts">
import { computed, ref } from "vue";

import BackendStatus from "../components/BackendStatus.vue";

// 登录/注册切换（SRS §6）。骨架阶段只做 UI：/auth/login、/auth/register 尚未进入
// api-types.ts，提交逻辑待认证票接入——契约生成前不手写请求形状（D13）。
type Mode = "login" | "register";

const mode = ref<Mode>("login");
const username = ref("");
const password = ref("");

const isLogin = computed(() => mode.value === "login");
</script>

<template>
  <section class="card auth-card">
    <div class="tabs" role="tablist">
      <button
        type="button"
        role="tab"
        :aria-selected="isLogin"
        :class="{ active: isLogin }"
        @click="mode = 'login'"
      >
        登录
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="!isLogin"
        :class="{ active: !isLogin }"
        @click="mode = 'register'"
      >
        注册
      </button>
    </div>

    <form class="auth-form" @submit.prevent>
      <label>
        用户名
        <input
          v-model="username"
          name="username"
          required
          minlength="3"
          maxlength="20"
          autocomplete="username"
          placeholder="3–20 个字符"
        />
      </label>
      <label>
        密码
        <input
          v-model="password"
          type="password"
          name="password"
          required
          minlength="6"
          :autocomplete="isLogin ? 'current-password' : 'new-password'"
          placeholder="至少 6 位"
        />
      </label>
      <button type="submit" disabled title="认证端点待后端认证票落地后接入">
        {{ isLogin ? "登录" : "注册并登录" }}
      </button>
      <p class="muted note">骨架阶段：提交动作在认证端点进入契约（api-types.ts）后接入。</p>
    </form>

    <BackendStatus />
  </section>
</template>
