import { ref } from 'vue'
import router from './router'

export const toast = ref(null)
let toastTimer
export function notify(message, kind = 'ok') {
  toast.value = { message, kind }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = null), 4000)
}

export async function api(path, { method = 'GET', body, params } = {}) {
  let url = '/api' + path
  if (params) {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') q.set(k, v)
    const s = q.toString()
    if (s) url += '?' + s
  }
  const res = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 && !path.startsWith('/login') && path !== '/me') {
    router.push('/login')
    throw new Error('Please sign in')
  }
  let data = null
  try { data = await res.json() } catch { /* empty body */ }
  if (!res.ok) {
    const d = data?.detail
    const msg = typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => x.msg).join('; ') : `Request failed (${res.status})`
    throw new Error(msg)
  }
  return data
}

// Run an async action, show errors as a toast.
export async function attempt(fn, okMessage) {
  try {
    const r = await fn()
    if (okMessage) notify(okMessage)
    return r
  } catch (e) {
    notify(e.message, 'err')
    return undefined
  }
}

export const imageUrl = (visitId, thumb = false) => `/api/visits/${visitId}/image${thumb ? '?thumb=true' : ''}`

export function fmtDateTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function fmtDay(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export const cameraLabel = (c) => ({ front_door: 'Front door', indoor: 'Indoor', enrollment: 'Enrolled photo', dashboard: 'Dashboard' }[c] || c)

export const ANNOUNCED = {
  sent: ['Spoken', 'ok'],
  dry_run: ['Dry run', 'info'],
  muted: ['Muted', 'warn'],
  quiet_hours: ['Quiet hours', 'warn'],
  cooldown: ['Repeat (cooldown)', 'muted'],
  none: ['Not announced', 'muted'],
  pending: ['Sending…', 'info'],
  failed: ['Failed', 'err'],
  disabled: ['HA not configured', 'warn'],
}
