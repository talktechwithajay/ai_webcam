<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { api, attempt, notify } from '../api'

const s = ref(null)
const mode = ref('days') // days | never
const days = ref(90)
const preview = ref(null)

async function load() {
  s.value = await attempt(() => api('/settings'))
  if (!s.value) return
  mode.value = s.value.retention_days === 'never' ? 'never' : 'days'
  days.value = s.value.retention_days === 'never' ? 90 : s.value.retention_days
  refreshPreview()
}
onMounted(load)

async function refreshPreview() {
  if (mode.value === 'never') { preview.value = { would_delete: 0 }; return }
  const d = Number(days.value)
  if (!Number.isInteger(d) || d < 1) return
  preview.value = await attempt(() => api('/retention/preview', { params: { days: d } }))
}
watch([mode, days], refreshPreview)

const retentionDirty = computed(() => s.value && (mode.value === 'never' ? 'never' : Number(days.value)) !== s.value.retention_days)

async function saveRetention() {
  const value = mode.value === 'never' ? 'never' : Number(days.value)
  const r = await attempt(() => api('/settings', { method: 'PUT', body: { retention_days: value } }),
    value === 'never' ? 'Unknown pictures will be kept forever' : `Unknown pictures are now kept for ${value} days`)
  if (r) s.value = r
}
async function purgeNow() {
  if (!confirm(`Delete ${preview.value.would_delete} picture(s) of unknown people older than ${days.value} days now?`)) return
  const r = await attempt(() => api('/retention/run', { method: 'POST' }))
  if (r) { notify(`Deleted ${r.deleted} visit(s)`); refreshPreview() }
}
async function put(key, v) {
  const r = await attempt(() => api('/settings', { method: 'PUT', body: { [key]: v } }), 'Saved')
  if (r) s.value = r
}
async function test() {
  const r = await attempt(() => api('/test-announcement', { method: 'POST' }))
  if (r) notify(`Test announcement: ${r.status}`, r.status === 'failed' ? 'err' : 'ok')
}
</script>

<template>
  <h1>Settings</h1>
  <p class="lead">Changes apply immediately.</p>
  <div v-if="s" class="stack">
    <section class="card stack" aria-labelledby="ret">
      <h2 id="ret">Keep pictures of unknown people</h2>
      <p class="muted small" style="margin: 0">Applies to people who have not been given a name. Pictures of named people are never deleted automatically.
        A cleanup runs every hour.</p>
      <label class="check"><input type="radio" value="days" v-model="mode" /> Delete after
        <input type="number" min="1" max="3650" v-model.number="days" :disabled="mode !== 'days'" style="width: 6rem" aria-label="Days to keep" /> days</label>
      <label class="check"><input type="radio" value="never" v-model="mode" /> Never delete</label>
      <div v-if="preview && mode === 'days'" class="small muted">
        Right now {{ preview.would_delete }} unknown-visitor picture(s) are older than {{ days }} days and would be deleted.
      </div>
      <div class="row">
        <button class="primary" :disabled="!retentionDirty" @click="saveRetention">Save</button>
        <button v-if="mode === 'days'" :disabled="!preview?.would_delete || retentionDirty" @click="purgeNow">Delete old pictures now…</button>
      </div>
    </section>

    <section class="card stack" aria-labelledby="speak">
      <h2 id="speak">Speaking on Alexa</h2>
      <label class="check"><input type="checkbox" :checked="!s.dry_run" @change="put('dry_run', !$event.target.checked)" />
        Send real announcements to Home Assistant / Alexa</label>
      <div class="small muted">Off = dry-run: everything is logged on the Visits page but nothing is spoken. Turn on once the test announcement works.</div>
      <div><button @click="test">Send a test announcement</button></div>
    </section>

    <section class="card stack" aria-labelledby="quiet">
      <h2 id="quiet">Quiet hours</h2>
      <label class="check"><input type="checkbox" :checked="s.quiet_hours_enabled" @change="put('quiet_hours_enabled', $event.target.checked)" />
        Stay silent during quiet hours (visits are still logged)</label>
      <div class="row">
        <label class="field">From <input type="time" :value="s.quiet_start" :disabled="!s.quiet_hours_enabled" @change="put('quiet_start', $event.target.value)" /></label>
        <label class="field">Until <input type="time" :value="s.quiet_end" :disabled="!s.quiet_hours_enabled" @change="put('quiet_end', $event.target.value)" /></label>
      </div>
    </section>

    <section class="card stack" aria-labelledby="cam">
      <h2 id="cam">Indoor camera</h2>
      <label class="check"><input type="checkbox" :checked="s.indoor_log_unknown" @change="put('indoor_log_unknown', $event.target.checked)" />
        Also record unrecognised people seen indoors (as unknown)</label>
      <div class="small muted">Off by default: indoors only enrolled people are logged.</div>
    </section>
  </div>
</template>
