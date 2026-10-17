<script setup>
import { ref } from 'vue'
import { api, attempt } from '../api'

const props = defineProps({ person: Object, compact: Boolean })
const emit = defineEmits(['done'])
const name = ref(props.person.status === 'enrolled' ? props.person.name : '')
const busy = ref(false)

async function save() {
  if (!name.value.trim()) return
  busy.value = true
  const r = await attempt(
    () => api(`/people/${props.person.id}/name`, { method: 'POST', body: { name: name.value } }),
    `Saved. All ${props.person.visit_count} visit(s) now show “${name.value.trim()}”.`,
  )
  busy.value = false
  if (r) emit('done', r)
}
</script>

<template>
  <form class="row" @submit.prevent="save">
    <input v-model="name" :placeholder="person.status === 'unknown' ? 'Enter name…' : 'Rename…'" maxlength="40"
           :aria-label="`Name for ${person.label}`" required />
    <button class="primary" :disabled="busy || !name.trim()">{{ person.status === 'unknown' ? 'Save name' : 'Rename' }}</button>
  </form>
</template>
