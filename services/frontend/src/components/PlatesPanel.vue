<script setup>
import { computed, reactive, ref } from 'vue'

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
const showPlateForm = ref(false)
const showRequestForm = ref(false)

const pendingCount = computed(() => props.pendingRequests.length)
const activePlatesCount = computed(() => props.allowedPlates.filter((plate) => plate.is_active).length)

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
  showPlateForm.value = false
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
  showRequestForm.value = false
}

function editAllowedPlate(item) {
  editAllowedPlateId.value = item.id
  form.plate_number = item.plate_number
  form.allowed_days = String(item.allowed_days).split(',').map((part) => part.trim())
  form.time_start = item.time_start
  form.time_end = item.time_end
  form.is_active = Boolean(item.is_active)
  showPlateForm.value = true
}

function editRequest(item) {
  requestForm.id = item.id
  requestForm.plate_number = item.plate_number
  requestForm.allowed_days = String(item.allowed_days).split(',').map((part) => part.trim())
  requestForm.time_start = item.time_start
  requestForm.time_end = item.time_end
  showRequestForm.value = true
}

function togglePlateForm() {
  if (editAllowedPlateId.value) {
    resetPlateForm()
    return
  }
  showPlateForm.value = !showPlateForm.value
}

function toggleRequestForm() {
  if (requestForm.id) {
    resetRequestForm()
    return
  }
  showRequestForm.value = !showRequestForm.value
}
</script>

<template>
  <header class="ws-header">
    <div class="ws-heading">
      <p class="ws-eyebrow">Рабочая зона</p>
      <h2>Допуски и заявки</h2>
      <p class="ws-sub">Сначала разбираем заявки, затем поддерживаем актуальный список постоянных допусков.</p>
    </div>
    <div class="ws-actions">
      <button type="button" @click="toggleRequestForm">
        {{ showRequestForm ? 'Скрыть форму заявки' : (requestForm.id ? 'Редактировать заявку' : 'Тестовая заявка от водителя') }}
      </button>
      <button type="button" class="primary" @click="togglePlateForm">
        {{ showPlateForm ? 'Скрыть форму допуска' : (editAllowedPlateId ? 'Редактировать допуск' : 'Добавить допуск') }}
      </button>
    </div>
  </header>

  <section class="surface surface--priority">
    <div class="surface-head">
      <div>
        <h3>Заявки на одобрение</h3>
        <p class="muted">Поступают от водителей. Охранник проверяет и принимает или отклоняет их.</p>
      </div>
      <span class="counter-pill" :class="{ 'counter-pill--alert': pendingCount > 0 }">{{ pendingCount }}</span>
    </div>
    <div v-if="pendingRequests.length" class="request-row">
      <article v-for="request in pendingRequests" :key="request.id" class="request-card">
        <div class="request-card__head">
          <strong class="data-code">{{ request.plate_number }}</strong>
          <span class="pill-inline">Ожидает</span>
        </div>
        <p class="muted">{{ formatDays(request.allowed_days) }} · {{ request.time_start }}–{{ request.time_end }}</p>
        <div class="row-actions">
          <button type="button" class="success" @click="emit('approve', request.id)">Одобрить</button>
          <button type="button" @click="editRequest(request)">Изменить</button>
          <button type="button" class="danger" @click="emit('reject', request.id)">Отклонить</button>
        </div>
      </article>
    </div>
    <div v-else class="empty-state">
      <p><strong>Очередь чистая.</strong></p>
      <p class="muted">Новые заявки от водителей появятся здесь автоматически.</p>
    </div>
  </section>

  <section class="surface">
    <div class="surface-head">
      <div>
        <h3>Постоянные допуски</h3>
        <p class="muted">Активные правила доступа на текущей парковке.</p>
      </div>
      <span class="counter-pill">{{ activePlatesCount }} / {{ allowedPlates.length }}</span>
    </div>
    <div class="data-region">
      <table class="table table--dense">
        <thead>
          <tr>
            <th>Номер</th>
            <th>Дни</th>
            <th>С</th>
            <th>По</th>
            <th>Статус</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="plate in allowedPlates" :key="plate.id">
            <td class="data-code">{{ plate.plate_number }}</td>
            <td>{{ formatDays(plate.allowed_days) }}</td>
            <td class="data-code">{{ plate.time_start }}</td>
            <td class="data-code">{{ plate.time_end }}</td>
            <td>
              <span class="status-tag" :class="plate.is_active ? 'status-tag--ok' : 'status-tag--off'">
                {{ plate.is_active ? 'Активен' : 'Отключен' }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button type="button" @click="editAllowedPlate(plate)">Изменить</button>
                <button type="button" class="danger" @click="emit('delete-plate', plate.id)">Удалить</button>
              </div>
            </td>
          </tr>
          <tr v-if="!allowedPlates.length">
            <td colspan="6" class="empty-cell">
              <div class="empty-inline">
                <p><strong>Допусков пока нет.</strong></p>
                <p class="muted">Добавьте номер вручную или одобрите заявку выше, чтобы он попал сюда.</p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section v-if="showPlateForm" class="surface surface--form">
    <div class="surface-head">
      <div>
        <h3>{{ editAllowedPlateId ? 'Изменить допуск' : 'Новый допуск' }}</h3>
        <p class="muted">Укажите номер, расписание и активность правила.</p>
      </div>
    </div>
    <form class="form-grid" @submit.prevent="submitPlate">
      <label class="field">
        Номер
        <input v-model.trim="form.plate_number" required placeholder="A123BC777" />
      </label>
      <label class="field">
        Время начала
        <input v-model="form.time_start" required type="time" />
      </label>
      <label class="field">
        Время окончания
        <input v-model="form.time_end" required type="time" />
      </label>
      <div class="field field--full">
        <span class="field-label">Дни недели</span>
        <div class="weekday-picker">
          <label v-for="day in weekdays" :key="`allowed-${day.value}`" class="weekday-item">
            <input v-model="form.allowed_days" type="checkbox" :value="day.value" />
            {{ day.label }}
          </label>
        </div>
      </div>
      <label class="checkbox field-inline">
        <input v-model="form.is_active" type="checkbox" />
        Допуск активен
      </label>
      <div class="form-actions field--full">
        <button type="submit" class="primary">
          {{ editAllowedPlateId ? 'Сохранить изменения' : 'Создать допуск' }}
        </button>
        <button type="button" @click="resetPlateForm">Отмена</button>
      </div>
    </form>
  </section>

  <section v-if="showRequestForm" class="surface surface--form">
    <div class="surface-head">
      <div>
        <h3>{{ requestForm.id ? 'Изменить заявку' : 'Тестовая заявка от водителя' }}</h3>
        <p class="muted">Этот блок имитирует подачу заявки водителем. Для повседневной работы он не нужен.</p>
      </div>
    </div>
    <form class="form-grid" @submit.prevent="submitRequest">
      <label class="field">
        Номер
        <input v-model.trim="requestForm.plate_number" required placeholder="A123BC777" />
      </label>
      <label class="field">
        Время начала
        <input v-model="requestForm.time_start" required type="time" />
      </label>
      <label class="field">
        Время окончания
        <input v-model="requestForm.time_end" required type="time" />
      </label>
      <div class="field field--full">
        <span class="field-label">Дни недели</span>
        <div class="weekday-picker">
          <label v-for="day in weekdays" :key="`request-${day.value}`" class="weekday-item">
            <input v-model="requestForm.allowed_days" type="checkbox" :value="day.value" />
            {{ day.label }}
          </label>
        </div>
      </div>
      <div class="form-actions field--full">
        <button type="submit" class="primary">{{ requestForm.id ? 'Сохранить заявку' : 'Отправить заявку' }}</button>
        <button type="button" @click="resetRequestForm">Отмена</button>
      </div>
    </form>
  </section>
</template>
