<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, toast } from './api'
import { markSignedIn } from './router'

const route = useRoute()
const router = useRouter()
const status = ref(null)
const open = ref(false)

async function loadStatus() {
  if (route.meta.public) return
  try { status.value = await api('/status') } catch { /* redirected to login */ }
}
onMounted(() => router.isReady().then(loadStatus))
watch(() => route.fullPath, () => { open.value = false; loadStatus() })

async function logout() {
  await api('/logout', { method: 'POST' })
  markSignedIn(false)
  router.push('/login')
}

const links = [
  ['/visits', 'Visits'], ['/visitors', 'Visitors'], ['/unknown', 'Unknown people'],
  ['/messages', 'Indoor messages'], ['/announcements', 'Announcements'], ['/cameras', 'Cameras'], ['/settings', 'Settings'],
]
</script>

<template>
  <router-view v-if="route.meta.public" />
  <div v-else class="layout">
    <button class="menu-btn" @click="open = !open" aria-label="Menu">☰ Menu</button>
    <nav class="sidebar" :class="{ open }" aria-label="Main">
      <div class="brand">🏠 Home Visitors</div>
      <router-link v-for="[to, label] in links" :key="to" :to="to" class="nav">{{ label }}</router-link>
      <div class="spacer"></div>
      <button @click="logout">Sign out</button>
    </nav>
    <main class="content">
      <div v-if="status?.global_mute" class="banner">All announcements are muted. <router-link to="/announcements">Change</router-link></div>
      <div v-if="status?.dry_run" class="banner">
        Dry-run mode: announcements are logged here but <strong>not spoken</strong> on Alexa.
        <router-link to="/settings">Turn on real announcements</router-link>
      </div>
      <div v-if="status && !status.recognition_ready" class="banner">
        Face models are not installed, so nothing is being recognised. Run <code>python tools/download_models.py</code> and restart.
      </div>
      <router-view />
    </main>
  </div>
  <div v-if="toast" class="toast" :class="toast.kind" role="status">{{ toast.message }}</div>
</template>
