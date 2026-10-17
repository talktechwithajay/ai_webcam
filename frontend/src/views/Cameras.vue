<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api, attempt, cameraLabel } from '../api'

const status = ref(null)
const live = ref({})
let timer
async function load() { status.value = await attempt(() => api('/status')) }
onMounted(() => { load(); timer = setInterval(load, 5000) })
onUnmounted(() => clearInterval(timer))
const KIND = { online: 'ok', connecting: 'info', offline: 'err', disabled: 'muted' }
</script>

<template>
  <h1>Cameras</h1>
  <p class="lead">Live status of each camera. Previews are shown only while you are signed in.</p>
  <div v-if="status" class="grid" style="grid-template-columns: repeat(auto-fill, minmax(340px, 1fr))">
    <div v-for="c in status.cameras" :key="c.id" class="card stack">
      <div class="row">
        <h2 style="margin: 0">{{ cameraLabel(c.id) }}</h2>
        <span class="badge right" :class="KIND[c.state]">{{ c.state }}</span>
      </div>
      <div class="small muted">
        Role: {{ c.role }} · Source: {{ c.source }}
        <template v-if="c.size"> · {{ c.size[0] }}×{{ c.size[1] }} · {{ c.fps }} fps</template>
      </div>
      <div v-if="c.error" class="small" style="color: var(--err)">{{ c.error }}</div>
      <div v-if="c.last_error" class="small" style="color: var(--err)">Processing error: {{ c.last_error }}</div>
      <img v-if="live[c.id]" class="preview" :src="`/api/cameras/${c.id}/preview.mjpg`" :alt="`Live view of ${c.label}`" />
      <div v-if="c.state === 'online'">
        <button @click="live[c.id] = !live[c.id]">{{ live[c.id] ? 'Hide live view' : 'Show live view' }}</button>
      </div>
      <div v-else-if="c.state === 'disabled'" class="small muted">Not configured. Set a source for this camera in config/settings.local.yaml.</div>
    </div>
    <div v-if="!status.cameras.length" class="card empty">No cameras configured. Edit config/settings.local.yaml, then run <code>check-cameras</code>.</div>
  </div>
  <div v-if="status" class="card row" style="margin-top: 1rem">
    <div><div class="stat">{{ status.stats.visits }}</div><div class="muted small">visits recorded</div></div>
    <div><div class="stat">{{ status.stats.known }}</div><div class="muted small">named people</div></div>
    <div><div class="stat">{{ status.stats.unknown }}</div><div class="muted small">unknown people</div></div>
    <div class="right small muted">Home Assistant: {{ status.home_assistant_enabled ? 'enabled' : 'not configured' }}
      <template v-if="status.last_announcement"> · last: {{ status.last_announcement.status }}</template></div>
  </div>
</template>
