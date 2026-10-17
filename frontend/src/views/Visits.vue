<script setup>
import { ref, reactive, watch, onMounted, onUnmounted, computed } from 'vue'
import { api, attempt, imageUrl, fmtDateTime, cameraLabel, ANNOUNCED, fmtDay } from '../api'
import DateFilter from '../components/DateFilter.vue'
import PhotoModal from '../components/PhotoModal.vue'
import NameForm from '../components/NameForm.vue'

const PAGE = 25
const range = ref({ from: fmtDay(new Date(Date.now() - 6 * 864e5)), to: fmtDay(new Date()) })
const filters = reactive({ camera: '', kind: 'all' })
const page = ref(0)
const data = ref({ total: 0, items: [] })
const loading = ref(false)
const zoom = ref(null)
const naming = ref(null)
let timer

async function load() {
  loading.value = true
  const r = await attempt(() => api('/visits', {
    params: { date_from: range.value.from, date_to: range.value.to, camera: filters.camera, kind: filters.kind, limit: PAGE, offset: page.value * PAGE },
  }))
  if (r) data.value = r
  loading.value = false
}
watch([range, () => filters.camera, () => filters.kind], () => { page.value = 0; load() })
watch(page, load)
onMounted(() => { load(); timer = setInterval(() => { if (page.value === 0 && !naming.value) load() }, 15000) })
onUnmounted(() => clearInterval(timer))

const pages = computed(() => Math.max(1, Math.ceil(data.value.total / PAGE)))

async function remove(v) {
  if (!confirm(`Delete this picture of ${v.label} from ${fmtDateTime(v.ts)}?`)) return
  if (await attempt(() => api(`/visits/${v.id}`, { method: 'DELETE' }), 'Deleted')) load()
}
function named(p) { naming.value = null; load() }
</script>

<template>
  <h1>Visits</h1>
  <p class="lead">Everyone the cameras noticed — one row per person, with the captured picture.</p>

  <div class="card stack" style="margin-bottom: 1rem">
    <DateFilter v-model="range" />
    <div class="row">
      <label class="field">Camera
        <select v-model="filters.camera">
          <option value="">All cameras</option><option value="front_door">Front door</option><option value="indoor">Indoor</option>
        </select>
      </label>
      <label class="field">Who
        <select v-model="filters.kind">
          <option value="all">Known and unknown</option><option value="known">Known only</option><option value="unknown">Unknown only</option>
        </select>
      </label>
      <span class="muted right">{{ data.total }} visit{{ data.total === 1 ? '' : 's' }}</span>
    </div>
  </div>

  <div v-if="!loading && !data.items.length" class="card empty">No visits in this period.</div>
  <div v-else class="table-wrap">
    <table>
      <thead><tr><th>Picture</th><th>Who</th><th>When</th><th>Camera</th><th>Announcement</th><th></th></tr></thead>
      <tbody>
        <tr v-for="v in data.items" :key="v.id">
          <td><img class="thumb" :src="imageUrl(v.id, true)" :alt="`Picture of ${v.label}`" loading="lazy" @click="zoom = v" /></td>
          <td>
            <router-link :to="`/visitors/${v.person_id}`" :class="{ 'unknown-label': v.status === 'unknown' }">{{ v.label }}</router-link>
            <div v-if="v.status === 'unknown'" style="margin-top: .3rem">
              <button class="small" v-if="naming !== v.id" @click="naming = v.id">Name this person</button>
              <NameForm v-else :person="{ id: v.person_id, label: v.label, status: 'unknown', visit_count: '' }" @done="named" />
            </div>
          </td>
          <td>{{ fmtDateTime(v.ts) }}</td>
          <td>{{ cameraLabel(v.camera) }}</td>
          <td>
            <span class="badge" :class="ANNOUNCED[v.announced]?.[1]">{{ ANNOUNCED[v.announced]?.[0] || v.announced }}</span>
            <div v-if="v.message" class="muted small">“{{ v.message }}”</div>
          </td>
          <td><button class="small danger" @click="remove(v)" :aria-label="`Delete visit ${v.id}`">Delete</button></td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="pager" v-if="pages > 1">
    <button :disabled="page === 0" @click="page--">← Newer</button>
    <span class="muted">Page {{ page + 1 }} of {{ pages }}</span>
    <button :disabled="page + 1 >= pages" @click="page++">Older →</button>
  </div>
  <PhotoModal :visit="zoom" @close="zoom = null" />
</template>
