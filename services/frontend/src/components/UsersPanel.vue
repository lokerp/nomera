<script setup>
import { computed, reactive, ref } from 'vue'

const props = defineProps({
  users: { type: Array, required: true },
  parkingLots: { type: Array, required: true }
})
const emit = defineEmits(['save-user', 'delete-user'])

const form = reactive({
  username: '',
  password: '',
  role: 'guard',
  parking_lot_ids: []
})
const showForm = ref(false)

const parkingLotNamesById = computed(() =>
  Object.fromEntries(props.parkingLots.map((lot) => [lot.id, lot.name]))
)

const adminCount = computed(() => props.users.filter((user) => user.role === 'admin').length)
const guardCount = computed(() => props.users.filter((user) => user.role !== 'admin').length)

function formatParkingLots(ids) {
  if (!ids?.length) return '—'
  const names = ids.map((id) => parkingLotNamesById.value[id]).filter(Boolean)
  return names.length ? names.join(', ') : ids.join(', ')
}

function toggleParkingLot(id) {
  if (form.parking_lot_ids.includes(id)) {
    form.parking_lot_ids = form.parking_lot_ids.filter((value) => value !== id)
  } else {
    form.parking_lot_ids = [...form.parking_lot_ids, id]
  }
}

function submit() {
  emit('save-user', { ...form })
  resetForm()
}

function resetForm() {
  form.username = ''
  form.password = ''
  form.role = 'guard'
  form.parking_lot_ids = []
  showForm.value = false
}

function toggleForm() {
  showForm.value = !showForm.value
}
</script>

<template>
  <header class="ws-header">
    <div class="ws-heading">
      <p class="ws-eyebrow">Рабочая зона</p>
      <h2>Пользователи и доступы</h2>
      <p class="ws-sub">Учетные записи администраторов и охранников и их доступ к парковкам.</p>
    </div>
    <div class="ws-actions">
      <button type="button" class="primary" @click="toggleForm">
        {{ showForm ? 'Скрыть форму' : 'Добавить пользователя' }}
      </button>
    </div>
  </header>

  <section class="surface">
    <div class="surface-head">
      <div>
        <h3>Учетные записи</h3>
        <p class="muted">Администраторы управляют системой, охранники работают на смене.</p>
      </div>
      <div class="role-counters">
        <span class="status-tag status-tag--ok">Админов: {{ adminCount }}</span>
        <span class="status-tag status-tag--off">Охранников: {{ guardCount }}</span>
      </div>
    </div>
    <div class="data-region">
      <table class="table table--dense">
        <thead>
          <tr>
            <th>Логин</th>
            <th>Роль</th>
            <th>Парковки</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td class="data-code">{{ user.username }}</td>
            <td>
              <span class="status-tag" :class="user.role === 'admin' ? 'status-tag--ok' : 'status-tag--off'">
                {{ user.role === 'admin' ? 'Администратор' : 'Охранник' }}
              </span>
            </td>
            <td>{{ formatParkingLots(user.parking_lot_ids) }}</td>
            <td>
              <div class="row-actions">
                <button type="button" class="danger" @click="emit('delete-user', user.id)">Удалить</button>
              </div>
            </td>
          </tr>
          <tr v-if="!users.length">
            <td colspan="4" class="empty-cell">
              <div class="empty-inline">
                <p><strong>Пользователей пока нет.</strong></p>
                <p class="muted">Добавьте администратора или охранника, чтобы начать работу.</p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section v-if="showForm" class="surface surface--form">
    <div class="surface-head">
      <div>
        <h3>Новый пользователь</h3>
        <p class="muted">Выберите роль и парковки. Охранник видит только привязанные парковки.</p>
      </div>
    </div>
    <form class="form-grid" @submit.prevent="submit">
      <label class="field">
        Логин
        <input v-model.trim="form.username" required autocomplete="username" placeholder="Логин" />
      </label>
      <label class="field">
        Пароль
        <input v-model="form.password" required type="password" autocomplete="new-password" placeholder="Пароль" />
      </label>
      <label class="field">
        Роль
        <select v-model="form.role">
          <option value="guard">Охранник</option>
          <option value="admin">Администратор</option>
        </select>
      </label>
      <div class="field field--full">
        <span class="field-label">Парковки</span>
        <div class="chips">
          <label v-for="lot in parkingLots" :key="lot.id" class="checkbox">
            <input type="checkbox" :checked="form.parking_lot_ids.includes(lot.id)" @change="toggleParkingLot(lot.id)" />
            {{ lot.name }}
          </label>
          <p v-if="!parkingLots.length" class="muted">Сначала создайте парковку.</p>
        </div>
      </div>
      <div class="form-actions field--full">
        <button type="submit" class="primary">Создать пользователя</button>
        <button type="button" @click="resetForm">Отмена</button>
      </div>
    </form>
  </section>
</template>
