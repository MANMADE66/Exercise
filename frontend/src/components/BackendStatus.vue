<script setup lang="ts">
import { onMounted, ref } from "vue";

import { getHealth, type HealthResponse } from "../api";

const health = ref<HealthResponse | null>(null);
const error = ref<string | null>(null);
const loading = ref(false);

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    health.value = await getHealth();
  } catch (cause) {
    health.value = null;
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="status">
    <span class="dot" :data-ok="health !== null"></span>
    <span v-if="health">后端在线 · API {{ health.version }}</span>
    <span v-else-if="loading" class="muted">检查后端连接…</span>
    <span v-else class="muted">后端未连上</span>
    <button type="button" :disabled="loading" @click="load">重新检查</button>
  </div>
  <p v-if="error" class="error">{{ error }}</p>
</template>
