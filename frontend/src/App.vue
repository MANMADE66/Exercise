<script setup lang="ts">
import TopBar from "./components/TopBar.vue";
</script>

<template>
  <!-- 外壳（HLD §4.1、spec 决策 7）：.wrap = v1 base.html 的 980px 居中容器 -->
  <div class="wrap">
    <TopBar />
    <RouterView />
  </div>
</template>
