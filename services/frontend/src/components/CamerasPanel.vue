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
  'delete-camera'
])

const localError = ref('')
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
  mp4_loop: true
})

const selectedParking = computed(() => props.parkingLots.find((item) => item.id === props.selectedParkingLotId) || null)

function startEditParking(item) {
  editParkingId.value = item.id
  parkingForm.name = item.name
  parkingForm.description = item.description || ''
}

function resetParkingForm() {
  editParkingId.value = ''
  parkingForm.name = ''
  parkingForm.description = ''
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
  if (!mp4Url) return ''
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
  emit('save-camera', {
    id: cameraForm.id.trim(),
    name: cameraForm.name.trim(),
    stream_url: streamUrl,
    parking_lot_id: props.selectedParkingLotId
  })
  cameraForm.id = ''
  cameraForm.name = ''
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
</script>

<template>
  <section class="card">
    <div class="section-header">
      <h2>Парковки</h2>
      <span class="muted">{{ parkingLots.length }} шт.</span>
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
      <div v-if="!parkingLots.length" class="empty-card">Пока нет парковок. Создайте первую.</div>
    </div>

    <form v-if="isAdmin" class="inline-form" @submit.prevent="submitParking">
      <input v-model.trim="parkingForm.name" required placeholder="Название парковки" />
      <input v-model.trim="parkingForm.description" placeholder="Описание (опционально)" />
      <button type="submit" class="primary">{{ editParkingId ? 'Сохранить' : 'Добавить парковку' }}</button>
      <button v-if="editParkingId" type="button" @click="resetParkingForm">Отмена</button>
    </form>

    <div v-if="isAdmin && selectedParking" class="actions">
      <button type="button" @click="startEditParking(selectedParking)">Редактировать выбранную</button>
      <button type="button" class="danger" @click="emit('delete-parking', selectedParking.id)">Удалить выбранную</button>
    </div>
  </section>

  <section class="card">
    <div class="section-header">
      <h2>Камеры выбранной парковки</h2>
      <span class="muted">{{ selectedParking?.name || 'Парковка не выбрана' }}</span>
    </div>
    <table class="table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Название</th>
          <th>Тип источника</th>
          <th>Ссылка / путь</th>
          <th v-if="isAdmin">Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="camera in cameras" :key="camera.id">
          <td>{{ camera.id }}</td>
          <td>{{ camera.name }}</td>
          <td><span class="pill-inline">{{ detectStreamType(camera.stream_url) }}</span></td>
          <td class="truncate">{{ camera.stream_url }}</td>
          <td v-if="isAdmin">
            <button type="button" class="danger" @click="emit('delete-camera', camera.id)">Удалить</button>
          </td>
        </tr>
        <tr v-if="!cameras.length">
          <td :colspan="isAdmin ? 5 : 4" class="empty-cell">В этой парковке пока нет камер</td>
        </tr>
      </tbody>
    </table>

    <form v-if="isAdmin" class="stacked-form" @submit.prevent="submitCamera">
      <div class="inline-form">
        <input v-model.trim="cameraForm.id" required placeholder="Идентификатор камеры (например, gate-1)" />
        <input v-model.trim="cameraForm.name" required placeholder="Название камеры" />
        <select v-model="cameraForm.source_type">
          <option value="rtsp">RTSP</option>
          <option value="https">HTTPS / HLS (.m3u8)</option>
          <option value="mp4">MP4 тест (loop)</option>
        </select>
      </div>

      <input
        v-if="cameraForm.source_type === 'rtsp'"
        v-model.trim="cameraForm.rtsp_url"
        required
        placeholder="rtsp://логин:пароль@host:port/stream"
      />
      <input
        v-else-if="cameraForm.source_type === 'https'"
        v-model.trim="cameraForm.https_url"
        required
        placeholder="https://host/path/stream.m3u8?token=..."
      />
      <div v-else class="inline-form">
        <input
          v-model.trim="cameraForm.mp4_path"
          required
          placeholder="https://host/test.mp4 или /opt/videos/test.mp4"
        />
        <label class="checkbox">
          <input v-model="cameraForm.mp4_loop" type="checkbox" />
          Крутить в цикле (loop=1)
        </label>
      </div>

      <button type="submit" class="primary">Добавить камеру</button>
      <p v-if="localError" class="error">{{ localError }}</p>
    </form>
  </section>
</template>
