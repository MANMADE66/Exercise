<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import { errorMessage, login, register } from "../api";
import BackendStatus from "../components/BackendStatus.vue";
import { setSession } from "../stores";

// 登录/注册切换（SRS §6）。请求形状来自 api.ts 的生成类型（D13），不在此手写。
type Mode = "login" | "register";

const router = useRouter();
const mode = ref<Mode>("login");
const username = ref("");
const password = ref("");
const submitting = ref(false);
const error = ref<string | null>(null);

const isLogin = computed(() => mode.value === "login");

function switchMode(next: Mode): void {
  mode.value = next;
  error.value = null;
}

/** 注册即登录（FR-1.4）：两种模式成功后都是「写会话 → 回月历」。 */
async function submit(): Promise<void> {
  if (submitting.value) return;
  submitting.value = true;
  error.value = null;
  try {
    const credentials = { username: username.value, password: password.value };
    const result = isLogin.value ? await login(credentials) : await register(credentials);
    setSession(result.token, result.user);
    await router.replace({ name: "calendar" });
  } catch (cause) {
    // api.ts 已把错误体归一为中文消息（401 统一文案 / 409 用户名占用 / 422 字段校验）
    error.value = errorMessage(cause);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <section class="card auth-card">
    <div class="tabs" role="tablist">
      <button
        type="button"
        role="tab"
        :aria-selected="isLogin"
        :class="{ active: isLogin }"
        @click="switchMode('login')"
      >
        登录
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="!isLogin"
        :class="{ active: !isLogin }"
        @click="switchMode('register')"
      >
        注册
      </button>
    </div>

    <form class="auth-form" @submit.prevent="submit">
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
      <button type="submit" :disabled="submitting">
        {{ submitting ? "请稍候…" : isLogin ? "登录" : "注册并登录" }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
    </form>

    <BackendStatus />
  </section>
</template>
