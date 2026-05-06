<script setup>
import { reactive } from 'vue'

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

function toggleParkingLot(id) {
  if (form.parking_lot_ids.includes(id)) {
    form.parking_lot_ids = form.parking_lot_ids.filter((value) => value !== id)
  } else {
    form.parking_lot_ids = [...form.parking_lot_ids, id]
  }
}

function submit() {
  emit('save-user', { ...form })
  form.username = ''
  form.password = ''
  form.role = 'guard'
  form.parking_lot_ids = []
}
</script>

<template>
  <section class="card">
    <h2>Охранники и привязки парковок</h2>
    <table class="table">
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
          <td>{{ user.username }}</td>
          <td>{{ user.role === 'admin' ? 'Администратор' : 'Охранник' }}</td>
          <td>{{ user.parking_lot_ids.join(', ') || '-' }}</td>
          <td><button type="button" class="danger" @click="emit('delete-user', user.id)">Удалить</button></td>
        </tr>
      </tbody>
    </table>
  </section>

  <section class="card">
    <h2>Добавить пользователя</h2>
    <form class="stacked-form" @submit.prevent="submit">
      <input v-model.trim="form.username" required placeholder="Логин" />
      <input v-model="form.password" required type="password" placeholder="Пароль" />
      <select v-model="form.role">
        <option value="guard">Охранник</option>
        <option value="admin">Администратор</option>
      </select>
      <div>
        <p class="muted">Парковки</p>
        <div class="chips">
          <label v-for="lot in parkingLots" :key="lot.id" class="checkbox">
            <input type="checkbox" :checked="form.parking_lot_ids.includes(lot.id)" @change="toggleParkingLot(lot.id)" />
            {{ lot.name }}
          </label>
        </div>
      </div>
      <button type="submit" class="primary">Создать</button>
    </form>
  </section>
</template>
