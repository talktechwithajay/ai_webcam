<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { api, attempt } from '../api'

const route = useRoute()
const people = ref([])
const messages = ref([])
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const blank = () => ({ id: null, person_id: Number(route.query.person) || '', text: '', start_date: '', end_date: '', weekdays: [], enabled: true })
const form = ref(blank())
const filterPerson = ref(route.query.person || '')

async function load() {
  const [p, m] = await Promise.all([attempt(() => api('/people', { params: { status: 'enrolled' } })), attempt(() => api('/messages'))])
  people.value = p || []
  messages.value = m || []
}
onMounted(load)
const shown = computed(() => messages.value.filter((m) => !filterPerson.value || m.person_id === Number(filterPerson.value)))
const preview = computed(() => form.value.text.trim())

async function save() {
  const f = form.value
  const body = { person_id: Number(f.person_id), text: f.text, start_date: f.start_date || null, end_date: f.end_date || null, weekdays: f.weekdays, enabled: f.enabled }
  const r = await attempt(() => api(f.id ? `/messages/${f.id}` : '/messages', { method: f.id ? 'PUT' : 'POST', body }), 'Message saved')
  if (r) { form.value = blank(); load() }
}
function edit(m) { form.value = { ...m, start_date: m.start_date || '', end_date: m.end_date || '' }; window.scrollTo({ top: 0, behavior: 'smooth' }) }
async function remove(m) {
  if (!confirm('Delete this message?')) return
  if (await attempt(() => api(`/messages/${m.id}`, { method: 'DELETE' }), 'Deleted')) load()
}
function when(m) {
  const parts = []
  if (m.weekdays.length) parts.push(m.weekdays.map((d) => DAYS[d]).join(', '))
  if (m.start_date || m.end_date) parts.push(`${m.start_date || '…'} to ${m.end_date || '…'}`)
  return parts.join(' · ') || 'Every day'
}
function toggleDay(d) {
  const w = form.value.weekdays
  form.value.weekdays = w.includes(d) ? w.filter((x) => x !== d) : [...w, d].sort()
}
</script>

<template>
  <h1>Indoor messages</h1>
  <p class="lead">When the indoor camera recognises someone, Alexa says their message. With no message set, it says “Welcome home, &lt;name&gt;.”
    Only named people can have messages.</p>

  <form class="card stack" style="margin-bottom: 1.5rem" @submit.prevent="save">
    <h2>{{ form.id ? 'Edit message' : 'New message' }}</h2>
    <div class="row">
      <label class="field">Person
        <select v-model="form.person_id" required>
          <option value="" disabled>Choose…</option>
          <option v-for="p in people" :key="p.id" :value="p.id">{{ p.label }}</option>
        </select>
      </label>
      <label class="check"><input type="checkbox" v-model="form.enabled" /> Active</label>
    </div>
    <label class="field">What Alexa should say
      <textarea v-model="form.text" maxlength="200" required placeholder="Welcome Naresh, today please make Aloo Paratha!"></textarea>
    </label>
    <div class="small muted">Letters, digits, spaces and . , ! ? : ' - only (max 200). {{ form.text.length }}/200</div>
    <div class="row">
      <label class="field">From date (optional) <input type="date" v-model="form.start_date" /></label>
      <label class="field">Until date (optional) <input type="date" v-model="form.end_date" /></label>
    </div>
    <div>
      <div class="small muted">Only on these weekdays (none selected = every day)</div>
      <div class="chips">
        <button v-for="(d, i) in DAYS" :key="d" type="button" class="chip" :class="{ on: form.weekdays.includes(i) }" @click="toggleDay(i)">{{ d }}</button>
      </div>
    </div>
    <div v-if="preview" class="card" style="background: var(--surface-2)"><span class="muted small">Alexa will say:</span> “{{ preview }}”</div>
    <div class="row">
      <button class="primary" :disabled="!form.person_id || !form.text.trim()">{{ form.id ? 'Update' : 'Add message' }}</button>
      <button v-if="form.id" type="button" @click="form = blank()">Cancel edit</button>
    </div>
  </form>

  <div class="row" style="margin-bottom: .75rem">
    <h2 style="margin: 0">Saved messages</h2>
    <select v-model="filterPerson" class="right" aria-label="Filter by person">
      <option value="">Everyone</option><option v-for="p in people" :key="p.id" :value="p.id">{{ p.label }}</option>
    </select>
  </div>
  <div v-if="!shown.length" class="card empty">No messages yet.</div>
  <div v-else class="table-wrap">
    <table>
      <thead><tr><th>Person</th><th>Message</th><th>When</th><th>Status</th><th></th></tr></thead>
      <tbody>
        <tr v-for="m in shown" :key="m.id">
          <td>{{ m.person_name }}</td><td>“{{ m.text }}”</td><td>{{ when(m) }}</td>
          <td><span class="badge" :class="m.enabled ? 'ok' : 'muted'">{{ m.enabled ? 'Active' : 'Off' }}</span></td>
          <td><div class="row"><button class="small" @click="edit(m)">Edit</button><button class="small danger" @click="remove(m)">Delete</button></div></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
