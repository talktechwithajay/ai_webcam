import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
  { path: '/', redirect: '/visits' },
  { path: '/visits', component: () => import('./views/Visits.vue'), meta: { title: 'Visits' } },
  { path: '/visitors', component: () => import('./views/Visitors.vue'), meta: { title: 'Visitors' } },
  { path: '/visitors/:id', component: () => import('./views/VisitorDetail.vue'), meta: { title: 'Visitor' } },
  { path: '/unknown', component: () => import('./views/Unknown.vue'), meta: { title: 'Unknown people' } },
  { path: '/messages', component: () => import('./views/Messages.vue'), meta: { title: 'Indoor messages' } },
  { path: '/announcements', component: () => import('./views/Announcements.vue'), meta: { title: 'Announcements' } },
  { path: '/cameras', component: () => import('./views/Cameras.vue'), meta: { title: 'Cameras' } },
  { path: '/settings', component: () => import('./views/Settings.vue'), meta: { title: 'Settings' } },
]

const router = createRouter({ history: createWebHistory(), routes })

let signedIn = null
router.beforeEach(async (to) => {
  if (to.meta.public) return true
  if (signedIn === null || signedIn === false) {
    try {
      const r = await fetch('/api/me', { credentials: 'same-origin' })
      signedIn = (await r.json()).signed_in
    } catch { signedIn = false }
  }
  return signedIn ? true : '/login'
})
export function markSignedIn(v) { signedIn = v }

export default router
