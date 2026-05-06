import { createRouter, createWebHistory } from 'vue-router'

import { useAuth } from '../composables/useAuth'
import LoginView from '../views/LoginView.vue'
import ParkingAppView from '../views/ParkingAppView.vue'

const routes = [
  { path: '/login', name: 'login', component: LoginView },
  { path: '/', name: 'app', component: ParkingAppView, meta: { requiresAuth: true } }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const { isAuthenticated } = useAuth()
  if (to.meta.requiresAuth && !isAuthenticated.value) {
    return { name: 'login' }
  }
  if (to.name === 'login' && isAuthenticated.value) {
    return { name: 'app' }
  }
  return true
})

export default router
