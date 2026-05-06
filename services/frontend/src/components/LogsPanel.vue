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
const liveAspectRatio = ref(16 / 9)
let websocket = null
let reconnectTimer = null
let hls = null

const liveCamera = computed(() => props.cameras.find((camera) => camera.id === liveCameraId.value) || null)
const overlayDetection = computed(() => latestConfirmedByCamera.value[liveCameraId.value] || null)
const liveStreamHint = computed(() => {
  if (!liveCamera.value) return 'Выберите камеру в селекторе ниже.'
  return `Источник: ${liveCamera.value.stream_url}`
})
const liveFrameStyle = computed(() => {
  const ratio = liveAspectRatio.value && Number.isFinite(liveAspectRatio.value) ? liveAspectRatio.value : 16 / 9
  return {
    aspectRatio: String(ratio),
    maxWidth: `calc(70vh * ${ratio})`
  }
})

function syncVideoAspect() {
  const video = liveVideoRef.value
  if (video && video.videoWidth && video.videoHeight) {
    liveAspectRatio.value = video.videoWidth / video.videoHeight
  }
}

function onVideoMetadata() {
  syncVideoAspect()
}

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
  <header class="ws-header">
    <div class="ws-heading">
      <p class="ws-eyebrow">Рабочая зона</p>
      <h2>История и аналитика</h2>
      <p class="ws-sub">Прямой эфир камеры, ключевые показатели и журнал распознаваний за выбранную парковку.</p>
    </div>
    <div class="ws-actions">
      <label class="inline-field">
        Камера в эфире
        <select v-model="liveCameraId">
          <option v-for="camera in cameras" :key="camera.id" :value="camera.id">{{ camera.name }}</option>
        </select>
      </label>
    </div>
  </header>

  <section class="surface surface--media">
    <div class="surface-head">
      <div>
        <h3>Прямой эфир</h3>
        <p class="muted">{{ liveStreamHint }}</p>
      </div>
      <span class="status-tag" :class="overlayDetection ? 'status-tag--ok' : 'status-tag--off'">
        {{ overlayDetection ? 'Распознано сейчас' : 'Ожидание распознавания' }}
      </span>
    </div>
    <div class="live-frame" :style="liveFrameStyle">
      <video
        ref="liveVideoRef"
        class="live-video"
        controls
        autoplay
        muted
        playsinline
        @loadedmetadata="onVideoMetadata"
        @resize="onVideoMetadata"
      />
      <div v-if="overlayDetection" class="bbox-live" :style="liveOverlayStyle()">
        <span>{{ overlayDetection.plate_text }}</span>
      </div>
    </div>
    <p v-if="liveError" class="error" role="alert" aria-live="polite">{{ liveError }}</p>
  </section>

  <section class="surface">
    <div class="surface-head">
      <div>
        <h3>Аналитика за сегодня</h3>
        <p class="muted">Сводные показатели обновляются в реальном времени.</p>
      </div>
    </div>
    <div class="kpi-grid">
      <article class="kpi">
        <span class="kpi-label">Распознаваний</span>
        <strong class="kpi-value">{{ stats.recognitions_today || 0 }}</strong>
        <span class="kpi-hint muted">Подтвержденных событий за день.</span>
      </article>
      <article class="kpi">
        <span class="kpi-label">Уникальных машин</span>
        <strong class="kpi-value">{{ stats.unique_plates_today || 0 }}</strong>
        <span class="kpi-hint muted">Сколько разных номеров видели.</span>
      </article>
      <article class="kpi">
        <span class="kpi-label">Пиковое время</span>
        <strong class="kpi-value">{{ stats.peak_hour || '—' }}</strong>
        <span class="kpi-hint muted">Час с наибольшей активностью.</span>
      </article>
    </div>
  </section>

  <section class="surface">
    <div class="surface-head">
      <div>
        <h3>Журнал распознаваний</h3>
        <p class="muted">Последние подтвержденные события на выбранной парковке.</p>
      </div>
      <label class="inline-field inline-field--end">
        Фильтр по камере
        <select :value="selectedCameraId" @change="emit('change-camera-filter', $event.target.value)">
          <option value="">Все камеры</option>
          <option v-for="camera in cameras" :key="camera.id" :value="camera.id">{{ camera.name }}</option>
        </select>
      </label>
    </div>
    <div class="data-region">
      <table class="table table--dense">
        <thead>
          <tr>
            <th>Камера</th>
            <th>Номер</th>
            <th>Время</th>
            <th>Снимок</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in logs" :key="item.id">
            <td class="data-code">{{ item.camera_id }}</td>
            <td class="data-code">{{ item.plate_number }}</td>
            <td class="data-code">{{ new Date(item.timestamp).toLocaleString() }}</td>
            <td>
              <button
                v-if="item.photo_url"
                type="button"
                class="thumb-wrap thumb-button"
                @click="openPhoto(item)"
                :aria-label="`Открыть фото распознавания ${item.plate_number}`"
              >
                <img :src="`${API_BASE}${item.photo_url}`" alt="scan" class="thumb" />
              </button>
              <span v-else class="muted">нет</span>
            </td>
          </tr>
          <tr v-if="!logs.length">
            <td colspan="4" class="empty-cell">
              <div class="empty-inline">
                <p><strong>Событий пока нет.</strong></p>
                <p class="muted">Запустите распознавание или подождите подтвержденных событий.</p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <div v-if="selectedPhoto" class="modal" @click="selectedPhoto = ''">
    <div class="modal-photo-wrap" @click.stop>
      <button type="button" class="modal-close" @click="selectedPhoto = ''">Закрыть фото</button>
      <div class="modal-photo-frame">
        <img
          :src="`${API_BASE}${selectedPhoto.photo_url}`"
          :alt="`Фото распознавания ${selectedPhoto.plate_number}`"
          class="modal-img"
        />
        <div
          v-if="selectedPhoto.bbox_x1 !== null && selectedPhoto.frame_width > 0"
          class="bbox-modal"
          :style="overlayStyle(selectedPhoto)"
        >
          <span>{{ selectedPhoto.plate_number }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
