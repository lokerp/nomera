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
const latestConfirmedByCamera = ref({})
const liveError = ref('')
const liveAspectRatio = ref(16 / 9)
let websocket = null
let reconnectTimer = null
let hls = null

const activeCameraId = computed({
  get: () => props.selectedCameraId,
  set: (value) => emit('change-camera-filter', value)
})
const liveCamera = computed(() => props.cameras.find((camera) => camera.id === activeCameraId.value) || null)
const overlayDetection = computed(() => latestConfirmedByCamera.value[activeCameraId.value] || null)
const liveStreamHint = computed(() => {
  if (!liveCamera.value) return 'Выберите камеру в селекторе выше.'
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

function normalizedCorners(corners, frameW, frameH) {
  if (!Array.isArray(corners) || corners.length !== 4) return null
  if (!frameW || !frameH) return null
  const result = []
  for (const point of corners) {
    if (!Array.isArray(point) || point.length < 2) return null
    const x = Number(point[0])
    const y = Number(point[1])
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null
    // Heuristic: WS protocol allows either absolute pixels or normalized [0..1].
    const useNormalized = x <= 1 && y <= 1
    const nx = useNormalized ? x * 100 : (x / frameW) * 100
    const ny = useNormalized ? y * 100 : (y / frameH) * 100
    result.push([nx, ny])
  }
  return result
}

function pointsToSvgString(points) {
  return points.map(([x, y]) => `${x.toFixed(3)},${y.toFixed(3)}`).join(' ')
}

const livePolygon = computed(() => {
  const item = overlayDetection.value
  if (!item) return null
  return normalizedCorners(item.corners, item.frame_width, item.frame_height)
})

const modalPolygon = computed(() => {
  const item = selectedPhoto.value
  if (!item) return null
  return normalizedCorners(item.corners, item.frame_width, item.frame_height)
})

function polygonLabelStyle(points) {
  if (!points) return { display: 'none' }
  return { left: `${points[0][0]}%`, top: `${points[0][1]}%` }
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
    if (!value.length) {
      if (activeCameraId.value) activeCameraId.value = ''
      return
    }
    const stillExists = value.some((camera) => camera.id === activeCameraId.value)
    if (!stillExists) activeCameraId.value = value[0].id
  },
  { immediate: true }
)

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
      <p class="ws-sub">Сначала выберите камеру — прямой эфир, аналитика и журнал относятся к ней.</p>
    </div>
    <div class="ws-actions">
      <label class="inline-field">
        Камера
        <select v-model="activeCameraId">
          <option value="" disabled>Выберите камеру</option>
          <option v-for="camera in cameras" :key="camera.id" :value="camera.id">{{ camera.name }}</option>
        </select>
      </label>
    </div>
  </header>

  <div v-if="!cameras.length" class="empty-state">
    <p><strong>Камер пока нет.</strong></p>
    <p class="muted">Добавьте камеру на вкладке «Парковки», чтобы увидеть эфир и журнал.</p>
  </div>
  <div v-else-if="!activeCameraId" class="empty-state">
    <p><strong>Камера не выбрана.</strong></p>
    <p class="muted">Выберите камеру в селекторе выше, чтобы увидеть прямой эфир и события.</p>
  </div>

  <template v-else>
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
      <template v-if="overlayDetection && livePolygon">
        <svg
          class="bbox-svg"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <polygon :points="pointsToSvgString(livePolygon)" />
        </svg>
        <span class="bbox-label" :style="polygonLabelStyle(livePolygon)">
          {{ overlayDetection.plate_text }}
        </span>
      </template>
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
        <p class="muted">Последние подтвержденные события на выбранной камере.</p>
      </div>
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
  </template>

  <div v-if="selectedPhoto" class="modal" @click="selectedPhoto = ''">
    <div class="modal-photo-wrap" @click.stop>
      <button type="button" class="modal-close" @click="selectedPhoto = ''">Закрыть фото</button>
      <div class="modal-photo-frame">
        <img
          :src="`${API_BASE}${selectedPhoto.photo_url}`"
          :alt="`Фото распознавания ${selectedPhoto.plate_number}`"
          class="modal-img"
        />
        <template v-if="modalPolygon">
          <svg
            class="bbox-svg"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <polygon :points="pointsToSvgString(modalPolygon)" />
          </svg>
          <span class="bbox-label" :style="polygonLabelStyle(modalPolygon)">
            {{ selectedPhoto.plate_number }}
          </span>
        </template>
      </div>
    </div>
  </div>
</template>
