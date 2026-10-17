<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, attempt, imageUrl, fmtDateTime, cameraLabel, ANNOUNCED } from '../api'
import DateFilter from '../components/DateFilter.vue'
import PhotoModal from '../components/PhotoModal.vue'
import NameForm from '../components/NameForm.vue'

const PAGE = 20
const route = useRoute()
const router = useRouter()
const person = ref(null)
const others = ref([])
const range = ref({ from: '', to: '' })
const order = ref('desc')
const page = ref(0)
const data = ref({ total: 0, items: [] })
const zoom = ref(null)
const mergeTarget = ref('')
const id = computed(() => Number(route.params.id))

async function loadPerson() {
  person.value = await attempt(() => api(`/people/${id.value}`))
  const all = await attempt(() => api('/people', { params: { status: person.value?.status === 'unknown' ? '' : 'enrolled' } }))
  others.value = (all || []).filter((p) => p.id !== id.value && (person.value?.status === 'unknown' || p.status === 'enrolled'))
}
async function loadVisits() {
  const r = await attempt(() => api('/visits', { params: {
    person_id: id.value, date_from: range.value.from, date_to: range.value.to, order: order.value, limit: PAGE, offset: page.value * PAGE } }))
  if (r) data.value = r
}
onMounted(() => { loadPerson(); loadVisits() })
watch(id, () => { page.value = 0; loadPerson(); loadVisits() })
watch([range, order], () => { page.value = 0; loadVisits() })
watch(page, loadVisits)
const pages = computed(() => Math.max(1, Math.ceil(data.value.total / PAGE)))

async function toggleMute() {
  person.value = await attempt(() => api(`/people/${id.value}`, { method: 'PATCH', body: { muted: !person.value.muted } }),
    person.value.muted ? 'Announcements on for this person' : 'Announcements muted for this person')
}
async function merge() {
  if (!mergeTarget.value) return
  const target = others.value.find((p) => p.id === Number(mergeTarget.value))
  if (!confirm(`Merge ${person.value.label} into ${target.label}? All visits move to ${target.label}.`)) return
  const r = await attempt(() => api(`/people/${id.value}/merge`, { method: 'POST', body: { target_id: target.id } }), 'Merged')
  if (r) router.push(`/visitors/${r.id}`)
}
async function remove() {
  if (!confirm(`Delete ${person.value.label} and all ${person.value.visit_count} pictures? This cannot be undone.`)) return
  if (await attempt(() => api(`/people/${id.value}`, { method: 'DELETE' }), 'Deleted')) router.push('/visitors')
}
async function notThem(v) {
  if (!confirm('Move this visit to a new unknown person? Use this if the system matched the wrong person.')) return
  const r = await attempt(() => api(`/visits/${v.id}/assign`, { method: 'POST', body: {} }), 'Moved to a new unknown person')
  if (r) { loadPerson(); loadVisits() }
}
async function removeVisit(v) {
  if (!confirm(`Delete this picture from ${fmtDateTime(v.ts)}?`)) return
  if (await attempt(() => api(`/visits/${v.id}`, { method: 'DELETE' }), 'Deleted')) { loadPerson(); loadVisits() }
}
function renamed(p) { person.value = p; loadVisits() }
</script>

<template>
  <p><router-link to="/visitors">← All visitors</router-link></p>
  <div v-if="person" class="card stack" style="margin-bottom: 1rem">
    <div class="row">
      <img v-if="person.thumb_visit_id" class="thumb" style="width: 96px; height: 112px" :src="imageUrl(person.thumb_visit_id, true)" :alt="person.label" />
      <div>
        <h1 :class="{ 'unknown-label': person.status === 'unknown' }">{{ person.label }}</h1>
        <div class="muted">{{ person.visit_count }} visit(s) · first {{ fmtDateTime(person.first_seen) }} · last {{ fmtDateTime(person.last_seen) }}</div>
      </div>
      <button class="right" @click="toggleMute">{{ person.muted ? '🔇 Muted — click to unmute' : '🔔 Announcing — click to mute' }}</button>
    </div>
    <div class="row">
      <NameForm :person="person" @done="renamed" />
      <span v-if="person.status === 'unknown'" class="muted small">Saving a name renames every past visit of this person.</span>
    </div>
    <div class="row">
      <select v-model="mergeTarget" aria-label="Merge into">
        <option value="">Same person as…</option>
        <option v-for="p in others" :key="p.id" :value="p.id">{{ p.label }}</option>
      </select>
      <button :disabled="!mergeTarget" @click="merge">Merge</button>
      <router-link v-if="person.status === 'enrolled'" :to="`/messages?person=${person.id}`" class="btn">Indoor messages ({{ person.message_count }})</router-link>
      <button class="danger right" @click="remove">Delete person…</button>
    </div>
  </div>

  <div class="card stack" style="margin-bottom: 1rem">
    <DateFilter v-model="range" />
    <span class="muted small">{{ data.total }} visit(s) in this period</span>
  </div>

  <div v-if="!data.items.length" class="card empty">No visits in this period.</div>
  <div v-else class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Picture</th>
          <th class="sortable" @click="order = order === 'desc' ? 'asc' : 'desc'" aria-sort="none">Date &amp; time {{ order === 'desc' ? '↓' : '↑' }}</th>
          <th>Camera</th><th>Match</th><th>Announcement</th><th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="v in data.items" :key="v.id">
          <td><img class="thumb" :src="imageUrl(v.id, true)" :alt="`Picture from ${fmtDateTime(v.ts)}`" loading="lazy" @click="zoom = v" /></td>
          <td>{{ fmtDateTime(v.ts) }}</td>
          <td>{{ cameraLabel(v.camera) }}</td>
          <td>{{ v.confidence != null ? Math.round(v.confidence * 100) + '%' : '—' }}</td>
          <td>
            <span class="badge" :class="ANNOUNCED[v.announced]?.[1]">{{ ANNOUNCED[v.announced]?.[0] || v.announced }}</span>
            <div v-if="v.message" class="muted small">“{{ v.message }}”</div>
          </td>
          <td><div class="row">
            <button class="small" @click="notThem(v)" title="The system matched the wrong person">Not them</button>
            <button class="small danger" @click="removeVisit(v)">Delete</button>
          </div></td>
        </tr>
      </tbody>
    </table>
  </div>
  <div class="pager" v-if="pages > 1">
    <button :disabled="page === 0" @click="page--">← Previous</button>
    <span class="muted">Page {{ page + 1 }} of {{ pages }}</span>
    <button :disabled="page + 1 >= pages" @click="page++">Next →</button>
  </div>
  <PhotoModal :visit="zoom ? { ...zoom, label: person?.label } : null" @close="zoom = null" />
</template>
