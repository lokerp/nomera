import { computed, reactive } from 'vue'

const TOKEN_KEY = 'nomera_token'
const USER_KEY = 'nomera_user'

const state = reactive({
  token: localStorage.getItem(TOKEN_KEY) || '',
  user: localStorage.getItem(USER_KEY) ? JSON.parse(localStorage.getItem(USER_KEY)) : null
})

export function useAuth() {
  const isAuthenticated = computed(() => Boolean(state.token))
  const isAdmin = computed(() => state.user?.role === 'admin')

  function setSession(token, user) {
    state.token = token
    state.user = user
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  }

  function clearSession() {
    state.token = ''
    state.user = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  return {
    state,
    isAuthenticated,
    isAdmin,
    setSession,
    clearSession
  }
}
