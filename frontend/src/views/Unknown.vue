<script setup>
import { ref, onMounted } from 'vue'
import { api, attempt, imageUrl, fmtDateTime } from '../api'
import NameForm from '../components/NameForm.vue'

const unknown = ref([])
const named = ref([])
const merge = ref({})
const loading = ref(true)

async function load() {
  const [u, n] = await Promise.all([
    attempt(() => api('/people', { params: { status: 'unknown' } })),
    attempt(() => api('/people', { params: { status: 'enrolled' } })),
  ])
  unknown.value = u || []
  named.value = n || []
  loading.value = false
}
onMounted(load)

async function doMerge(p) {
  const target = merge.value[p.id]
  if (!target) return
  const t = [...named.value, ...unknown.value].find((x) => x.id === Number(target))
  if (!confirm(`Merge ${p.label} into ${t.label}?`)) return
  if (await attempt(() => api(`/people/${p.id}/merge`, { method: 'POST', body: { target_id: t.id } }), 'Merged')) load()
}
async function remove(p) {
  if (!confirm(`Delete ${p.label} and all ${p.visit_count} picture(s)?`)) return
  if (await attempt(() => api(`/people/${p.id}`, { method: 'DELETE' }), 'Deleted')) load()
}
</script>

<template>
  <h1>Unknown people</h1>
  <p class="lead">Everyone the cameras noticed who is not in your list of named people, grouped by face.
    Give someone a name and every past visit is renamed instantly.</p>

  <div v-if="!loading && !unknown.length" class="card empty">No unknown people at the moment.</div>
  <div class="grid">
    <div v-for="p in unknown" :key="p.id" class="card stack">
      <router-link :to="`/visitors/${p.id}`">
        <img v-if="p.thumb_visit_id" class="thumb lg" :src="imageUrl(p.thumb_visit_id, true)" :alt="p.label" loading="lazy" />
      </router-link>
      <strong class="unknown-label">{{ p.label }}</strong>
      <div class="small muted">
        {{ p.visit_count }} visit{{ p.visit_count === 1 ? '' : 's' }}<br />
        First: {{ fmtDateTime(p.first_seen) }}<br />Last: {{ fmtDateTime(p.last_seen) }}
      </div>
      <NameForm :person="p" @done="load" />
      <div class="row">
        <select v-model="merge[p.id]" :aria-label="`Merge ${p.label} into`">
          <option value="">Same as…</option>
          <optgroup label="Named"><option v-for="n in named" :key="n.id" :value="n.id">{{ n.label }}</option></optgroup>
          <optgroup label="Unknown"><option v-for="u in unknown.filter((x) => x.id !== p.id)" :key="u.id" :value="u.id">{{ u.label }}</option></optgroup>
        </select>
        <button class="small" :disabled="!merge[p.id]" @click="doMerge(p)">Merge</button>
        <button class="small danger right" @click="remove(p)">Delete</button>
      </div>
    </div>
  </div>
</template>
