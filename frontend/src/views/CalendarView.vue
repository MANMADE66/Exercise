<script setup lang="ts">
import { session } from "../stores";
</script>

<template>
  <section class="card">
    <h1>月历</h1>
    <p class="muted">
      月历主页（含周体重列）骨架占位。交互平移清单（就地展开日详情、失焦 autosave、按计划预填、
      上移/下移、周体重列内提示）见 SRS §6，业务视图由后续票落地。
    </p>
    <p v-if="session.user" class="muted">当前用户：{{ session.user.username }}</p>
  </section>
</template>
