<script setup>
import { ref, onMounted } from 'vue'
import { api, attempt, imageUrl, notify } from '../api'

const settings = ref(null)
const people = ref([])

async function load() {
  settings.value = await attempt(() => api('/settings'))
  people.value = (await attempt(() => api('/people', { params: { status: 'enrolled' } }))) || []
}
onMounted(load)

async function setGlobal(v) {
  settings.value = await attempt(() => api('/mute-all', { method: 'POST', body: { muted: v } }), v ? 'Everything muted' : 'Announcements on')
}
async function setSetting(key, v) {
  settings.value = await attempt(() => api('/settings', { method: 'PUT', body: { [key]: v } }), 'Saved')
}
async function toggle(p) {
  const r = await attempt(() => api(`/people/${p.id}`, { method: 'PATCH', body: { muted: !p.muted } }))
  if (r) p.muted = r.muted
}
async function test() {
  const r = await attempt(() => api('/test-announcement', { method: 'POST' }))
  if (r) notify(r.status === 'sent' ? 'Test sent — listen for Alexa' : `Test result: ${r.status}`, r.status === 'failed' ? 'err' : 'ok')
}
</script>

<template>
  <h1>Announcements</h1>
  <p class="lead">Choose who gets announced. Muted people are still recognised and logged — Alexa just stays quiet.</p>

  <div v-if="settings" class="stack">
    <div class="card row">
      <div>
        <h2 style="margin: 0">Mute everything</h2>
        <div class="muted small">Switches off all announcements for everyone (front door and indoor).</div>
      </div>
      <label class="switch right">
        <input type="checkbox" role="switch" :checked="settings.global_mute" @change="setGlobal($event.target.checked)" />
        {{ settings.global_mute ? 'Muted' : 'Announcing' }}
      </label>
    </div>

    <div class="card stack">
      <h2>What gets announced</h2>
      <label class="check"><input type="checkbox" :checked="settings.welcome_enabled" @change="setSetting('welcome_enabled', $event.target.checked)" />
        Indoor camera: greet recognised people (welcome message or their custom message)</label>
      <label class="check"><input type="checkbox" :checked="settings.announce_unknown_front" @change="setSetting('announce_unknown_front', $event.target.checked)" />
        Front door: announce “Unknown visitor at the front door”</label>
      <div><button @click="test">Send a test announcement</button></div>
    </div>

    <h2 style="margin: .5rem 0 0">People</h2>
    <div v-if="!people.length" class="card empty">No named people yet. <router-link to="/visitors">Add or name someone</router-link>.</div>
    <div v-else class="table-wrap">
      <table>
        <thead><tr><th>Person</th><th>Announcements</th></tr></thead>
        <tbody>
          <tr v-for="p in people" :key="p.id">
            <td><div class="row">
              <img v-if="p.thumb_visit_id" class="thumb" style="width: 40px; height: 48px" :src="imageUrl(p.thumb_visit_id, true)" :alt="p.label" />
              <router-link :to="`/visitors/${p.id}`">{{ p.label }}</router-link>
            </div></td>
            <td>
              <label class="switch">
                <input type="checkbox" role="switch" :checked="!p.muted" :disabled="settings.global_mute" @change="toggle(p)" :aria-label="`Announce ${p.label}`" />
                {{ settings.global_mute ? 'Muted (everything)' : p.muted ? 'Muted' : 'Announced' }}
              </label>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
