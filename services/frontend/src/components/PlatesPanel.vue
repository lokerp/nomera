<script setup>
import { reactive, ref } from 'vue'

const props = defineProps({
  pendingRequests: { type: Array, required: true },
  allowedPlates: { type: Array, required: true },
  selectedParkingLotId: { type: String, required: true }
})

const emit = defineEmits([
  'approve',
  'reject',
  'save-plate',
  'update-plate',
  'delete-plate',
  'create-request',
  'update-request'
])

const weekdays = [
  { value: '1', label: 'Пн' },
  { value: '2', label: 'Вт' },
  { value: '3', label: 'Ср' },
  { value: '4', label: 'Чт' },
  { value: '5', label: 'Пт' },
  { value: '6', label: 'Сб' },
  { value: '7', label: 'Вс' }
]

const form = reactive({
  plate_number: '',
  allowed_days: ['1', '2', '3', '4', '5'],
  time_start: '08:00',
  time_end: '18:00',
  is_active: true
})
const requestForm = reactive({
  id: '',
  plate_number: '',
  allowed_days: ['1', '2', '3', '4', '5'],
  time_start: '08:00',
  time_end: '18:00'
})
const editAllowedPlateId = ref('')

function formatDays(value) {
  const set = new Set(String(value || '').split(',').map((item) => item.trim()))
  return weekdays.filter((day) => set.has(day.value)).map((day) => day.label).join(', ')
}

function sortDays(value) {
  return [...value].sort((a, b) => Number(a) - Number(b)).join(',')
}

function submitPlate() {
  const payload = {
    parking_lot_id: props.selectedParkingLotId,
    plate_number: form.plate_number,
    allowed_days: sortDays(form.allowed_days),
    time_start: form.time_start,
    time_end: form.time_end,
    is_active: form.is_active
  }
  if (editAllowedPlateId.value) {
    emit('update-plate', editAllowedPlateId.value, payload, resetPlateForm)
    return
  }
  emit('save-plate', payload, resetPlateForm)
}

function resetPlateForm() {
  form.plate_number = ''
  form.allowed_days = ['1', '2', '3', '4', '5']
  form.time_start = '08:00'
  form.time_end = '18:00'
  form.is_active = true
  editAllowedPlateId.value = ''
}

function submitRequest() {
  const payload = {
    parking_lot_id: props.selectedParkingLotId,
    plate_number: requestForm.plate_number,
    allowed_days: sortDays(requestForm.allowed_days),
    time_start: requestForm.time_start,
    time_end: requestForm.time_end
  }
  if (requestForm.id) {
    emit('update-request', requestForm.id, payload, resetRequestForm)
    return
  }
  emit('create-request', payload, resetRequestForm)
}

function resetRequestForm() {
  requestForm.id = ''
  requestForm.plate_number = ''
  requestForm.allowed_days = ['1', '2', '3', '4', '5']
  requestForm.time_start = '08:00'
  requestForm.time_end = '18:00'
}

function editAllowedPlate(item) {
  editAllowedPlateId.value = item.id
  form.plate_number = item.plate_number
  form.allowed_days = String(item.allowed_days).split(',').map((part) => part.trim())
  form.time_start = item.time_start
  form.time_end = item.time_end
  form.is_active = Boolean(item.is_active)
}

function editRequest(item) {
  requestForm.id = item.id
  requestForm.plate_number = item.plate_number
  requestForm.allowed_days = String(item.allowed_days).split(',').map((part) => part.trim())
  requestForm.time_start = item.time_start
  requestForm.time_end = item.time_end
}
</script>

<template>
  <section class="card">
    <h2>Новые заявки на доступ</h2>
    <div class="request-row">
      <article v-for="request in pendingRequests" :key="request.id" class="request-card">
        <strong>{{ request.plate_number }}</strong>
        <small>{{ formatDays(request.allowed_days) }} · {{ request.time_start }}-{{ request.time_end }}</small>
        <div class="actions">
          <button type="button" class="success" @click="emit('approve', request.id)">Одобрить</button>
          <button type="button" @click="editRequest(request)">Изменить</button>
          <button type="button" class="danger" @click="emit('reject', request.id)">Отклонить</button>
        </div>
      </article>
      <div v-if="!pendingRequests.length" class="empty-card">Новых заявок нет</div>
    </div>
  </section>

  <section class="card">
    <h2>Разрешенные номера</h2>
    <table class="table">
      <thead>
        <tr>
          <th>Номер</th>
          <th>Дни</th>
          <th>С</th>
          <th>По</th>
          <th>Активен</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="plate in allowedPlates" :key="plate.id">
          <td>{{ plate.plate_number }}</td>
          <td>{{ formatDays(plate.allowed_days) }}</td>
          <td>{{ plate.time_start }}</td>
          <td>{{ plate.time_end }}</td>
          <td>{{ plate.is_active ? 'Да' : 'Нет' }}</td>
          <td class="actions">
            <button type="button" @click="editAllowedPlate(plate)">Изменить</button>
            <button type="button" class="danger" @click="emit('delete-plate', plate.id)">Удалить</button>
          </td>
        </tr>
        <tr v-if="!allowedPlates.length">
          <td colspan="6" class="empty-cell">Список пуст</td>
        </tr>
      </tbody>
    </table>

    <form class="inline-form" @submit.prevent="submitPlate">
      <input v-model.trim="form.plate_number" required placeholder="A123BC777" />
      <div class="weekday-picker">
        <label v-for="day in weekdays" :key="`allowed-${day.value}`" class="weekday-item">
          <input v-model="form.allowed_days" type="checkbox" :value="day.value" />
          {{ day.label }}
        </label>
      </div>
      <input v-model="form.time_start" required type="time" />
      <input v-model="form.time_end" required type="time" />
      <label class="checkbox"><input v-model="form.is_active" type="checkbox" /> Активен</label>
      <button type="submit" class="primary">{{ editAllowedPlateId.value ? 'Сохранить' : 'Добавить' }}</button>
      <button v-if="editAllowedPlateId.value" type="button" @click="resetPlateForm">Отмена</button>
    </form>
  </section>

  <section class="card">
    <h2>Тест: создать заявку (охранник)</h2>
    <form class="inline-form" @submit.prevent="submitRequest">
      <input v-model.trim="requestForm.plate_number" required placeholder="A123BC777" />
      <div class="weekday-picker">
        <label v-for="day in weekdays" :key="`request-${day.value}`" class="weekday-item">
          <input v-model="requestForm.allowed_days" type="checkbox" :value="day.value" />
          {{ day.label }}
        </label>
      </div>
      <input v-model="requestForm.time_start" required type="time" />
      <input v-model="requestForm.time_end" required type="time" />
      <button type="submit" class="primary">{{ requestForm.id ? 'Сохранить заявку' : 'Отправить заявку' }}</button>
      <button v-if="requestForm.id" type="button" @click="resetRequestForm">Отмена</button>
    </form>
  </section>
</template>
