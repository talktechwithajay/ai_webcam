<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { markSignedIn } from '../router'

const router = useRouter()
const username = ref('admin')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  busy.value = true
  error.value = ''
  try {
    await api('/login', { method: 'POST', body: { username: username.value, password: password.value } })
    markSignedIn(true)
    router.push('/visits')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form class="card login stack" @submit.prevent="submit">
    <h1>🏠 Home Visitors</h1>
    <p class="muted">Sign in with the dashboard login from your settings file.</p>
    <label class="field">Username <input v-model="username" autocomplete="username" required /></label>
    <label class="field">Password <input v-model="password" type="password" autocomplete="current-password" required autofocus /></label>
    <p v-if="error" role="alert" style="color: var(--err); margin: 0">{{ error }}</p>
    <button class="primary" :disabled="busy">Sign in</button>
  </form>
</template>
