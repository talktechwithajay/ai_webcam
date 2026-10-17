<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, attempt, imageUrl, fmtDateTime, notify } from '../api'

const router = useRouter()
const people = ref([])
const tab = ref('all')
const search = ref('')
const showAdd = ref(false)
const form = ref({ name: '', consent: false, photos: [] })
const busy = ref(false)

async function load() {
  const r = await attempt(() => api('/people', { params: { status: tab.value === 'all' ? '' : tab.value, q: search.value } }))
  if (r) people.value = r
}
onMounted(load)
watch([tab, search], load)

function pickFiles(e) {
  const files = [...e.target.files].slice(0, 10)
  Promise.all(files.map((f) => new Promise((res) => {
    const fr = new FileReader()
    fr.onload = () => res(fr.result)
    fr.readAsDataURL(f)
  }))).then((urls) => (form.value.photos = urls))
}

async function enroll() {
  busy.value = true
  const r = await attempt(() => api('/people', { method: 'POST', body: {
    name: form.value.name, photos: form.value.photos, consent_confirmed: form.value.consent } }), 'Person added')
  busy.value = false
  if (r) { showAdd.value = false; form.value = { name: '', consent: false, photos: [] }; router.push(`/visitors/${r.id}`) }
}
</script>

<template>
  <div class="row">
    <div>
      <h1>Visitors</h1>
      <p class="lead">Every unique person the system knows about. Select one to see all of their visits.</p>
    </div>
    <button class="right primary" @click="showAdd = !showAdd">+ Add a person from photos</button>
  </div>

  <form v-if="showAdd" class="card stack" style="margin-bottom: 1rem" @submit.prevent="enroll">
    <h2>Add a known person</h2>
    <p class="muted small" style="margin: 0">Upload 1–10 clear photos with exactly one face each. Alternatively, name them from the
      <router-link to="/unknown">Unknown people</router-link> page after they have been seen by a camera.</p>
    <div class="row">
      <label class="field">Name <input v-model="form.name" maxlength="40" required /></label>
      <label class="field">Photos <input type="file" accept="image/*" multiple required @change="pickFiles" /></label>
    </div>
    <label class="check"><input type="checkbox" v-model="form.consent" /> This person has agreed to being recognised by the cameras.</label>
    <div class="row"><button class="primary" :disabled="busy || !form.consent || !form.photos.length">Add person</button>
      <button type="button" @click="showAdd = false">Cancel</button></div>
  </form>

  <div class="row" style="margin-bottom: 1rem">
    <div class="chips">
      <button class="chip" :class="{ on: tab === 'all' }" @click="tab = 'all'">Everyone</button>
      <button class="chip" :class="{ on: tab === 'enrolled' }" @click="tab = 'enrolled'">Named</button>
      <button class="chip" :class="{ on: tab === 'unknown' }" @click="tab = 'unknown'">Unknown</button>
    </div>
    <input v-model="search" type="search" placeholder="Search by name…" aria-label="Search visitors" class="right" />
  </div>

  <div v-if="!people.length" class="card empty">No visitors yet.</div>
  <div class="grid">
    <router-link v-for="p in people" :key="p.id" :to="`/visitors/${p.id}`" class="card stack" style="text-decoration: none; color: inherit">
      <img v-if="p.thumb_visit_id" class="thumb lg" :src="imageUrl(p.thumb_visit_id, true)" :alt="`Picture of ${p.label}`" loading="lazy" />
      <div v-else class="avatar" style="width: 100%; height: 190px">{{ (p.name || '?')[0] }}</div>
      <div class="row">
        <strong :class="{ 'unknown-label': p.status === 'unknown' }">{{ p.label }}</strong>
        <span v-if="p.muted" class="badge warn right">Muted</span>
      </div>
      <div class="small muted">
        {{ p.visit_count }} visit{{ p.visit_count === 1 ? '' : 's' }}<br />
        First: {{ fmtDateTime(p.first_seen) }}<br />Last: {{ fmtDateTime(p.last_seen) }}
      </div>
    </router-link>
  </div>
</template>
