<script setup>
import { imageUrl, fmtDateTime, cameraLabel } from '../api'
defineProps({ visit: Object })
defineEmits(['close'])
</script>

<template>
  <div v-if="visit" class="modal-back" @click.self="$emit('close')" @keydown.esc="$emit('close')">
    <div class="modal" role="dialog" aria-modal="true">
      <img class="full" :src="imageUrl(visit.id)" :alt="`Picture of ${visit.label}`" />
      <div class="row">
        <strong :class="{ 'unknown-label': visit.status === 'unknown' }">{{ visit.label }}</strong>
        <span class="muted">{{ cameraLabel(visit.camera) }} · {{ fmtDateTime(visit.ts) }}</span>
        <button class="right" autofocus @click="$emit('close')">Close</button>
      </div>
    </div>
  </div>
</template>
