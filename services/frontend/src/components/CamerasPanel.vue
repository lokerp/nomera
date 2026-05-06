<script setup>
import { computed, reactive, ref } from 'vue'

const props = defineProps({
  parkingLots: { type: Array, required: true },
  cameras: { type: Array, required: true },
  selectedParkingLotId: { type: String, default: '' },
  isAdmin: { type: Boolean, default: false }
})

const emit = defineEmits([
  'select-parking',
  'create-parking',
  'update-parking',
  'delete-parking',
  'save-camera',
  'update-camera',
  'delete-camera'
])

const localError = ref('')
const showParkingForm = ref(false)
const showCameraForm = ref(false)

const parkingForm = reactive({
  name: '',
  description: ''
})
const editParkingId = ref('')

const cameraForm = reactive({
  id: '',
  name: '',
  source_type: 'rtsp',
  rtsp_url: '',
  https_url: 'https://cam11.yar-net.ru/dmmZy7y9/mono.m3u8?token=ecf935d922147606ddf99edb965dfd7d',
  mp4_path: '',
  mp4_file: null,
  mp4_loop: true
})
const editCameraId = ref('')

const selectedParking = computed(() => props.parkingLots.find((item) => item.id === props.selectedParkingLotId) || null)

function startEditParking(item) {
  editParkingId.value = item.id
  parkingForm.name = item.name
  parkingForm.description = item.description || ''
  showParkingForm.value = true
}

function resetParkingForm() {
  editParkingId.value = ''
  parkingForm.name = ''
  parkingForm.description = ''
  showParkingForm.value = false
}

function submitParking() {
  const payload = {
    name: parkingForm.name.trim(),
    description: parkingForm.description.trim()
  }
  if (!payload.name) return
  if (editParkingId.value) {
    emit('update-parking', editParkingId.value, payload, resetParkingForm)
    return
  }
  emit('create-parking', payload, resetParkingForm)
}

function buildCameraUrl() {
  if (cameraForm.source_type === 'rtsp') {
    return cameraForm.rtsp_url.trim()
  }
  if (cameraForm.source_type === 'https') {
    return cameraForm.https_url.trim()
  }
  const mp4Url = cameraForm.mp4_path.trim()
  if (!mp4Url && !cameraForm.mp4_file) return ''
  if (!mp4Url && cameraForm.mp4_file) return '__UPLOAD__'
  if (!cameraForm.mp4_loop) return mp4Url
  if (mp4Url.includes('loop=')) return mp4Url
  return `${mp4Url}${mp4Url.includes('?') ? '&' : '?'}loop=1`
}

function submitCamera() {
  localError.value = ''
  if (!props.selectedParkingLotId) {
    localError.value = 'Сначала создайте или выберите парковку.'
    return
  }
  const streamUrl = buildCameraUrl()
  if (!streamUrl) {
    localError.value = 'Укажите источник потока камеры.'
    return
  }
  const payload = {
    id: cameraForm.id.trim(),
    name: cameraForm.name.trim(),
    stream_url: streamUrl,
    parking_lot_id: props.selectedParkingLotId,
    source_type: cameraForm.source_type,
    mp4_file: cameraForm.mp4_file,
    mp4_loop: cameraForm.mp4_loop
  }
  if (editCameraId.value) {
    emit('update-camera', editCameraId.value, payload, resetCameraForm)
    return
  }
  emit('save-camera', payload, resetCameraForm)
}

function resetCameraForm() {
  editCameraId.value = ''
  cameraForm.id = ''
  cameraForm.name = ''
  cameraForm.rtsp_url = ''
  cameraForm.mp4_path = ''
  cameraForm.mp4_file = null
  showCameraForm.value = false
}

function onMp4Selected(event) {
  const file = event.target.files?.[0]
  cameraForm.mp4_file = file || null
}

function startEditCamera(camera) {
  editCameraId.value = camera.id
  cameraForm.id = camera.id
  cameraForm.name = camera.name
  cameraForm.mp4_file = null
  showCameraForm.value = true
  const value = camera.stream_url || ''
  if (value.startsWith('rtsp://')) {
    cameraForm.source_type = 'rtsp'
    cameraForm.rtsp_url = value
    cameraForm.https_url = ''
    cameraForm.mp4_path = ''
    return
  }
  if (value.includes('.mp4')) {
    cameraForm.source_type = 'mp4'
    cameraForm.mp4_path = value
    cameraForm.rtsp_url = ''
    cameraForm.https_url = ''
    return
  }
  cameraForm.source_type = 'https'
  cameraForm.https_url = value
  cameraForm.rtsp_url = ''
  cameraForm.mp4_path = ''
}

function detectStreamType(streamUrl) {
  const value = (streamUrl || '').toLowerCase()
  if (value.startsWith('rtsp://')) return 'RTSP'
  if (value.includes('.m3u8')) return 'HTTPS (HLS)'
  if (value.includes('.mp4')) return 'MP4 (тест)'
  if (value.startsWith('https://')) return 'HTTPS'
  return 'Другой'
}

function toggleParkingForm() {
  if (editParkingId.value) {
    resetParkingForm()
    return
  }
  showParkingForm.value = !showParkingForm.value
}

function toggleCameraForm() {
  if (editCameraId.value) {
    resetCameraForm()
    return
  }
  showCameraForm.value = !showCameraForm.value
}
</script>

<template>
  <header class="ws-header">
    <div class="ws-heading">
      <p class="ws-eyebrow">Рабочая зона</p>
      <h2>Парковки и камеры</h2>
      <p class="ws-sub">Выберите площадку, чтобы управлять привязанными камерами и источниками видео.</p>
    </div>
    <div class="ws-actions">
      <button v-if="isAdmin" type="button" @click="toggleParkingForm">
        {{ showParkingForm ? 'Скрыть форму парковки' : (editParkingId ? 'Редактировать парковку' : 'Новая парковка') }}
      </button>
      <button v-if="isAdmin && selectedParkingLotId" type="button" class="primary" @click="toggleCameraForm">
        {{ showCameraForm ? 'Скрыть форму камеры' : (editCameraId ? 'Редактировать камеру' : 'Добавить камеру') }}
      </button>
    </div>
  </header>

  <section class="surface">
    <div class="surface-head">
      <div>
        <h3>Парковки</h3>
        <p class="muted">Выберите площадку для работы с камерами и допусками.</p>
      </div>
      <span class="counter-pill">{{ parkingLots.length }}</span>
    </div>

    <div class="parking-list">
      <button
        v-for="item in parkingLots"
        :key="item.id"
        type="button"
        class="parking-item"
        :class="{ active: item.id === selectedParkingLotId }"
        @click="emit('select-parking', item.id)"
      >
        <span>{{ item.name }}</span>
        <small class="muted">{{ item.description || 'Без описания' }}</small>
      </button>
      <div v-if="!parkingLots.length" class="empty-state">
        <p><strong>Парковок пока нет.</strong></p>
        <p class="muted">Создайте первую парковку, чтобы начать привязывать камеры и допуски.</p>
      </div>
    </div>

    <div v-if="isAdmin && selectedParking" class="surface-foot">
      <button type="button" @click="startEditParking(selectedParking)">Изменить парковку</button>
      <button type="button" class="danger" @click="emit('delete-parking', selectedParking.id)">Удалить парковку</button>
    </div>
  </section>

  <section v-if="isAdmin && showParkingForm" class="surface surface--form">
    <div class="surface-head">
      <div>
        <h3>{{ editParkingId ? 'Изменить парковку' : 'Новая парковка' }}</h3>
        <p class="muted">Минимум: название площадки. Описание помогает быстро ориентироваться при росте сети.</p>
      </div>
    </div>
    <form class="form-grid" @submit.prevent="submitParking">
      <label class="field">
        Название
        <input v-model.trim="parkingForm.name" required placeholder="Например, Гараж 1" />
      </label>
      <label class="field">
        Описание
        <input v-model.trim="parkingForm.description" placeholder="Например, главный въезд" />
      </label>
      <div class="form-actions field--full">
        <button type="submit" class="primary">{{ editParkingId ? 'Сохранить парковку' : 'Создать парковку' }}</button>
        <button type="button" @click="resetParkingForm">Отмена</button>
      </div>
    </form>
  </section>

  <section class="surface">
    <div class="surface-head">
      <div>
        <h3>Камеры площадки</h3>
        <p class="muted">{{ selectedParking?.name || 'Парковка не выбрана' }}</p>
      </div>
      <span class="counter-pill">{{ cameras.length }}</span>
    </div>
    <div class="data-region">
      <table class="table table--dense">
        <thead>
          <tr>
            <th>Идентификатор</th>
            <th>Название</th>
            <th>Тип</th>
            <th>Источник</th>
            <th v-if="isAdmin">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="camera in cameras" :key="camera.id">
            <td class="data-code">{{ camera.id }}</td>
            <td>{{ camera.name }}</td>
            <td><span class="pill-inline">{{ detectStreamType(camera.stream_url) }}</span></td>
            <td class="truncate data-code">{{ camera.stream_url }}</td>
            <td v-if="isAdmin">
              <div class="row-actions">
                <button type="button" @click="startEditCamera(camera)">Изменить</button>
                <button type="button" class="danger" @click="emit('delete-camera', camera.id)">Удалить</button>
              </div>
            </td>
          </tr>
          <tr v-if="!cameras.length">
            <td :colspan="isAdmin ? 5 : 4" class="empty-cell">
              <div class="empty-inline">
                <p><strong>Камеры еще не привязаны.</strong></p>
                <p class="muted">Добавьте RTSP, HLS поток или тестовый MP4, чтобы запустить распознавание.</p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section v-if="isAdmin && showCameraForm" class="surface surface--form">
    <div class="surface-head">
      <div>
        <h3>{{ editCameraId ? 'Изменить камеру' : 'Новая камера' }}</h3>
        <p class="muted">Сначала задайте идентификатор и название, затем выберите тип источника.</p>
      </div>
    </div>
    <form class="form-grid" @submit.prevent="submitCamera">
      <label class="field">
        Идентификатор
        <input v-model.trim="cameraForm.id" required placeholder="например, gate-1" />
      </label>
      <label class="field">
        Название
        <input v-model.trim="cameraForm.name" required placeholder="Название камеры" />
      </label>
      <label class="field">
        Тип источника
        <select v-model="cameraForm.source_type">
          <option value="rtsp">RTSP</option>
          <option value="https">HTTPS / HLS (.m3u8)</option>
          <option value="mp4">MP4 тест (цикл)</option>
        </select>
      </label>

      <label v-if="cameraForm.source_type === 'rtsp'" class="field field--full">
        RTSP адрес
        <input v-model.trim="cameraForm.rtsp_url" required placeholder="rtsp://логин:пароль@host:port/stream" />
      </label>
      <label v-else-if="cameraForm.source_type === 'https'" class="field field--full">
        HTTPS / HLS адрес
        <input v-model.trim="cameraForm.https_url" required placeholder="https://host/path/stream.m3u8?token=..." />
      </label>
      <template v-else>
        <label class="field field--full">
          Путь к MP4
          <input
            v-model.trim="cameraForm.mp4_path"
            required
            placeholder="https://host/test.mp4 или /opt/videos/test.mp4"
          />
        </label>
        <label class="field">
          Локальный файл
          <input type="file" accept="video/mp4,video/*" @change="onMp4Selected" />
        </label>
        <label class="checkbox field-inline">
          <input v-model="cameraForm.mp4_loop" type="checkbox" />
          Воспроизводить по кругу (loop=1)
        </label>
        <p class="hint field--full">Локальный файл .mp4 будет загружен на сервер и подменит URL.</p>
      </template>

      <div class="form-actions field--full">
        <button type="submit" class="primary">{{ editCameraId ? 'Сохранить камеру' : 'Создать камеру' }}</button>
        <button type="button" @click="resetCameraForm">Отмена</button>
      </div>
      <p v-if="localError" class="error field--full" role="alert" aria-live="polite">{{ localError }}</p>
    </form>
  </section>
</template>
