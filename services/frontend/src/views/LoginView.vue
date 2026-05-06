<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { apiRequest } from '../api/client'
import { useAuth } from '../composables/useAuth'

const router = useRouter()
const { setSession } = useAuth()

const form = ref({
  username: 'admin',
  password: 'admin123'
})
const error = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  error.value = ''
  try {
    const token = await apiRequest('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(form.value)
    })
    const me = await apiRequest('/api/auth/me', {
      headers: { Authorization: `Bearer ${token.access_token}` }
    })
    setSession(token.access_token, me)
    router.push({ name: 'app' })
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <form class="card auth-card" @submit.prevent="submit">
      <h1>Система парковки</h1>
      <p>Войдите, чтобы открыть панель управления парковками.</p>

      <label>
        Логин
        <input v-model.trim="form.username" autocomplete="username" placeholder="Введите логин" />
      </label>
      <label>
        Пароль
        <input v-model="form.password" type="password" autocomplete="current-password" placeholder="Введите пароль" />
      </label>
      <button type="submit" class="primary" :disabled="loading">{{ loading ? 'Вход...' : 'Войти' }}</button>
      <p v-if="error" class="error">{{ error }}</p>
    </form>
  </main>
</template>
