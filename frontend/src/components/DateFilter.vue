<script setup>
import { computed } from 'vue'
import { fmtDay } from '../api'

// v-model: { from: 'YYYY-MM-DD' | '', to: 'YYYY-MM-DD' | '' }
const model = defineModel({ type: Object, default: () => ({ from: '', to: '' }) })
function day(offset) { const d = new Date(); d.setDate(d.getDate() + offset); return fmtDay(d) }
const presets = [
  ['today', 'Today', () => ({ from: day(0), to: day(0) })],
  ['yesterday', 'Yesterday', () => ({ from: day(-1), to: day(-1) })],
  ['7', 'Last 7 days', () => ({ from: day(-6), to: day(0) })],
  ['30', 'Last 30 days', () => ({ from: day(-29), to: day(0) })],
  ['all', 'All time', () => ({ from: '', to: '' })],
]
const preset = computed(() => {
  const m = model.value
  return presets.find((p) => { const r = p[2](); return r.from === (m.from || '') && r.to === (m.to || '') })?.[0] || ''
})
function pick(p) { model.value = p[2]() }
function manual(k, v) { model.value = { ...model.value, [k]: v } }
</script>

<template>
  <div class="row">
    <div class="chips" role="group" aria-label="Quick date ranges">
      <button v-for="p in presets" :key="p[0]" class="chip" :class="{ on: preset === p[0] }" @click="pick(p)">{{ p[1] }}</button>
    </div>
    <label class="field">From
      <input type="date" :value="model.from" :max="model.to || undefined" @change="manual('from', $event.target.value)" />
    </label>
    <label class="field">To
      <input type="date" :value="model.to" :min="model.from || undefined" @change="manual('to', $event.target.value)" />
    </label>
  </div>
</template>
