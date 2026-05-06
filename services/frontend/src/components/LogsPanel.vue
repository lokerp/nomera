<script setup>
import Hls from 'hls.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { API_BASE } from '../api/client'

const props = defineProps({
  stats: { type: Object, required: true },
  logs: { type: Array, required: true },
  cameras: { type: Array, required: true },
  token: { type: String, default: '' },
  selectedCameraId: { type: String, default: '' }
})
const emit = defineEmits(['change-camera-filter', 'confirmed-detection'])

const selectedPhoto = ref('')
const liveVideoRef = ref(null)
const liveCameraId = ref('')
const latestConfirmedByCamera = ref({})
const liveError = ref('')
let websocket = null
let reconnectTimer = null
let hls = null

const liveCamera = computed(() => props.cameras.find((camera) => camera.id === liveCameraId.value) || null)
const overlayDetection = computed(() => {
  return latestConfirmedByCamera.value[liveCameraId.value] || null
})

async function openPhoto(item) {
  selectedPhoto.value = item
  await nextTick()
}

function overlayStyle(item) {
  if (item?.bbox_x1 === null || item?.bbox_x1 === undefined || !item.frame_width || !item.frame_height) return {}
  const useNormalized = item.bbox_x2 <= 1 && item.bbox_y2 <= 1
  const x = useNormalized ? item.bbox_x1 * 100 : (item.bbox_x1 / item.frame_width) * 100
  const y = useNormalized ? item.bbox_y1 * 100 : (item.bbox_y1 / item.frame_height) * 100
  const w = useNormalized
    ? (item.bbox_x2 - item.bbox_x1) * 100
    : ((item.bbox_x2 - item.bbox_x1) / item.frame_width) * 100
  const h = useNormalized
    ? (item.bbox_y2 - item.bbox_y1) * 100
    : ((item.bbox_y2 - item.bbox_y1) / item.frame_height) * 100
  return { left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%` }
}

function liveOverlayStyle() {
  const item = overlayDetection.value
  if (!item?.bbox || !item.frame_width || !item.frame_height) return {}
  const useNormalized = item.bbox.x2 <= 1 && item.bbox.y2 <= 1
  const x = useNormalized ? item.bbox.x1 * 100 : (item.bbox.x1 / item.frame_width) * 100
  const y = useNormalized ? item.bbox.y1 * 100 : (item.bbox.y1 / item.frame_height) * 100
  const w = useNormalized
    ? (item.bbox.x2 - item.bbox.x1) * 100
    : ((item.bbox.x2 - item.bbox.x1) / item.frame_width) * 100
  const h = useNormalized
    ? (item.bbox.y2 - item.bbox.y1) * 100
    : ((item.bbox.y2 - item.bbox.y1) / item.frame_height) * 100
  return { left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%` }
}

function connectWs() {
  if (!props.token) return
  clearTimeout(reconnectTimer)
  const wsBase = (import.meta.env.VITE_BACKEND_WS_URL || API_BASE.replace(/^http/, 'ws')).replace(/\/$/, '')
  websocket = new WebSocket(`${wsBase}/api/v1/ws?token=${encodeURIComponent(props.token)}`)

  websocket.onmessage = (event) => {
    const message = JSON.parse(event.data)
    if (message.type === 'confirmed_detection') {
      latestConfirmedByCamera.value = { ...latestConfirmedByCamera.value, [message.payload.camera_id]: message.payload }
      emit('confirmed-detection', message.payload)
    }
  }
  websocket.onclose = () => {
    reconnectTimer = setTimeout(connectWs, 1500)
  }
}

function destroyHls() {
  if (hls) {
    hls.destroy()
    hls = null
  }
}

function setupLivePlayer() {
  destroyHls()
  liveError.value = ''
  const video = liveVideoRef.value
  const streamUrl = liveCamera.value?.stream_url || ''
  if (!video || !streamUrl) return
  if (!streamUrl.toLowerCase().includes('.m3u8')) {
    video.src = streamUrl
    return
  }
  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = streamUrl
    return
  }
  if (Hls.isSupported()) {
    hls = new Hls()
    hls.loadSource(streamUrl)
    hls.attachMedia(video)
    hls.on(Hls.Events.ERROR, (_, data) => {
      if (data.fatal) liveError.value = 'Не удалось открыть live-поток камеры.'
    })
    return
  }
  liveError.value = 'Браузер не поддерживает HLS-поток.'
}

watch(
  () => props.cameras,
  (value) => {
    if (!liveCameraId.value && value.length) liveCameraId.value = value[0].id
  },
  { immediate: true }
)

watch(liveCameraId, () => setupLivePlayer())
watch(
  () => props.token,
  () => {
    websocket?.close()
    connectWs()
  }
)
watch(
  () => liveCamera.value?.stream_url,
  () => setupLivePlayer(),
  { immediate: true }
)

onMounted(async () => {
  connectWs()
  await nextTick()
  setupLivePlayer()
})
onBeforeUnmount(() => {
  clearTimeout(reconnectTimer)
  websocket?.close()
  destroyHls()
})
</script>

<template>
  <section class="card">
    <h2>Прямой эфир камеры</h2>
    <div class="inline-form">
      <label class="inline-field">
        Камера в live
        <select v-model="liveCameraId">
          <option v-for="camera in cameras" :key="camera.id" :value="camera.id">{{ camera.name }}</option>
        </select>
      </label>
    </div>
    <div class="live-wrap">
      <video ref="liveVideoRef" class="live-video" controls autoplay muted playsinline />
      <div v-if="overlayDetection" class="bbox-live" :style="liveOverlayStyle()">
        <span>{{ overlayDetection.plate_text }}</span>
      </div>
    </div>
    <p v-if="liveError" class="error">{{ liveError }}</p>
  </section>

  <section class="card">
    <h2>Аналитика за сегодня</h2>
    <div class="stats-grid">
      <article class="stat-card">
        <span>Распознаваний</span>
        <strong>{{ stats.recognitions_today || 0 }}</strong>
      </article>
      <article class="stat-card">
        <span>Уникальных машин</span>
        <strong>{{ stats.unique_plates_today || 0 }}</strong>
      </article>
      <article class="stat-card">
        <span>Пиковое время</span>
        <strong>{{ stats.peak_hour || '-' }}</strong>
      </article>
    </div>
  </section>

  <section class="card">
    <div class="section-header">
      <h2>Логи распознаваний</h2>
      <label class="inline-field">
        Фильтр по камере
        <select :value="selectedCameraId" @change="emit('change-camera-filter', $event.target.value)">
          <option value="">Все камеры</option>
          <option v-for="camera in cameras" :key="camera.id" :value="camera.id">{{ camera.name }}</option>
        </select>
      </label>
    </div>
    <table class="table">
      <thead>
        <tr>
          <th>ID камеры</th>
          <th>Номер</th>
          <th>Дата/время</th>
          <th>Фото</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in logs" :key="item.id">
          <td>{{ item.camera_id }}</td>
          <td>{{ item.plate_number }}</td>
          <td>{{ new Date(item.timestamp).toLocaleString() }}</td>
          <td>
            <div v-if="item.photo_url" class="thumb-wrap" @click="openPhoto(item)">
              <img :src="`${API_BASE}${item.photo_url}`" alt="scan" class="thumb" />
            </div>
            <span v-else class="muted">нет</span>
          </td>
        </tr>
        <tr v-if="!logs.length">
          <td colspan="4" class="empty-cell">Логи пока пустые</td>
        </tr>
      </tbody>
    </table>
  </section>

  <div v-if="selectedPhoto" class="modal" @click="selectedPhoto = ''">
    <div class="modal-photo-wrap">
      <img :src="`${API_BASE}${selectedPhoto.photo_url}`" alt="full" class="modal-img" />
      <div
        v-if="selectedPhoto.bbox_x1 !== null && selectedPhoto.frame_width > 0"
        class="bbox-modal"
        :style="overlayStyle(selectedPhoto)"
      >
        <span>{{ selectedPhoto.plate_number }}</span>
      </div>
    </div>
  </div>
</template>
