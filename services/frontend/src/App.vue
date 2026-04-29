<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  CirclePause,
  CirclePlay,
  PlugZap,
  RefreshCcw,
  Square,
  Wifi,
  WifiOff
} from 'lucide-vue-next'

const API_BASE = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8001'
const WS_URL = import.meta.env.VITE_BACKEND_WS_URL || API_BASE.replace(/^http/, 'ws') + '/api/v1/ws'
const VIDEO_URL = `${API_BASE}/api/v1/video`
const BUFFER_SECONDS = 2
const RESUME_MARGIN_SECONDS = 0.7
const BOX_HOLD_SECONDS = 0.45

const videoRef = ref(null)
const canvasRef = ref(null)
const wsState = ref('disconnected')
const mlStatus = ref('unknown')
const activeCamera = ref(null)
const confirmed = ref([])
const rawFrames = ref([])
const latestProcessedTime = ref(0)
const selectedRaw = ref(null)
const isBuffering = ref(false)
const isStarting = ref(false)
const isStopping = ref(false)
const errorMessage = ref('')

let websocket = null
let reconnectTimer = null
let animationFrame = null
let playbackStarted = false

const sortedRawFrames = computed(() => rawFrames.value)
const newestConfirmed = computed(() => confirmed.value.slice().reverse())
const hasConnection = computed(() => wsState.value === 'connected')
const cameraLabel = computed(() => activeCamera.value?.camera_id || 'default')
const processedLabel = computed(() => latestProcessedTime.value.toFixed(2))

function setError(message) {
  errorMessage.value = message
  if (message) {
    setTimeout(() => {
      if (errorMessage.value === message) errorMessage.value = ''
    }, 5000)
  }
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }
  return response.json()
}

async function refreshStatus() {
  try {
    const status = await apiRequest('/api/v1/ml/status')
    applyMlStatus(status)
  } catch (error) {
    setError(`ML status unavailable: ${error.message}`)
  }
}

function applyMlStatus(status) {
  mlStatus.value = status.status || 'unknown'
  activeCamera.value = status.cameras?.[0] || null
}

async function startMl() {
  isStarting.value = true
  setError('')
  resetPlayback()
  try {
    const status = await apiRequest('/api/v1/ml/start', { method: 'POST' })
    applyMlStatus(status)
  } catch (error) {
    setError(`Start failed: ${error.message}`)
  } finally {
    isStarting.value = false
  }
}

async function stopMl() {
  isStopping.value = true
  try {
    const status = await apiRequest('/api/v1/ml/stop', { method: 'POST' })
    applyMlStatus(status)
    pauseVideo()
  } catch (error) {
    setError(`Stop failed: ${error.message}`)
  } finally {
    isStopping.value = false
  }
}

function resetPlayback() {
  rawFrames.value = []
  selectedRaw.value = null
  latestProcessedTime.value = 0
  playbackStarted = false
  isBuffering.value = true
  const video = videoRef.value
  if (video) {
    video.pause()
    video.currentTime = 0
  }
  drawOverlay()
}

function pauseVideo() {
  const video = videoRef.value
  if (video) video.pause()
  isBuffering.value = false
}

async function startVideoIfBuffered() {
  if (playbackStarted || latestProcessedTime.value < BUFFER_SECONDS) return
  const video = videoRef.value
  if (!video) return

  playbackStarted = true
  isBuffering.value = false
  video.currentTime = 0
  try {
    await video.play()
  } catch {
    setError('Press play in the video panel to start playback')
  }
}

function appendRawFrame(payload) {
  rawFrames.value.push(payload)
  if (rawFrames.value.length > 2500) {
    rawFrames.value.splice(0, rawFrames.value.length - 2500)
  }
  latestProcessedTime.value = Math.max(latestProcessedTime.value, payload.timestamp_seconds || 0)
  startVideoIfBuffered()
}

function appendConfirmed(payload) {
  const exists = confirmed.value.some((item) => item.id === payload.id)
  if (!exists) {
    confirmed.value.push(payload)
    if (confirmed.value.length > 100) confirmed.value.shift()
  }
}

function connectWs() {
  clearTimeout(reconnectTimer)
  wsState.value = 'connecting'
  websocket = new WebSocket(WS_URL)

  websocket.onopen = () => {
    wsState.value = 'connected'
    refreshStatus()
  }

  websocket.onmessage = (event) => {
    const message = JSON.parse(event.data)
    if (message.type === 'history') {
      confirmed.value = message.payload.confirmed || []
      rawFrames.value = message.payload.raw || []
      latestProcessedTime.value = rawFrames.value.at(-1)?.timestamp_seconds || 0
      return
    }
    if (message.type === 'raw_detection') appendRawFrame(message.payload)
    if (message.type === 'confirmed_detection') appendConfirmed(message.payload)
    if (message.type === 'ml_status') applyMlStatus(message.payload)
  }

  websocket.onclose = () => {
    wsState.value = 'disconnected'
    reconnectTimer = setTimeout(connectWs, 1500)
  }

  websocket.onerror = () => {
    wsState.value = 'disconnected'
    websocket?.close()
  }
}

function pickRawForTime(currentTime) {
  const frames = sortedRawFrames.value
  if (!frames.length) return null

  let left = 0
  let right = frames.length - 1
  let best = null
  while (left <= right) {
    const mid = Math.floor((left + right) / 2)
    const item = frames[mid]
    if (item.timestamp_seconds <= currentTime + 0.08) {
      best = item
      left = mid + 1
    } else {
      right = mid - 1
    }
  }

  if (!best || currentTime - best.timestamp_seconds > BOX_HOLD_SECONDS) return null
  return best
}

function ensureCanvasSize() {
  const canvas = canvasRef.value
  const video = videoRef.value
  if (!canvas || !video) return null

  const rect = video.getBoundingClientRect()
  const dpr = window.devicePixelRatio || 1
  const width = Math.max(1, Math.round(rect.width * dpr))
  const height = Math.max(1, Math.round(rect.height * dpr))

  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width
    canvas.height = height
  }
  canvas.style.width = `${rect.width}px`
  canvas.style.height = `${rect.height}px`

  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  return { ctx, width: rect.width, height: rect.height }
}

function drawOverlay() {
  const canvasInfo = ensureCanvasSize()
  if (!canvasInfo) return
  const { ctx, width, height } = canvasInfo
  ctx.clearRect(0, 0, width, height)

  const raw = selectedRaw.value
  if (!raw?.detections?.length) return

  const scaleX = width / raw.frame_width
  const scaleY = height / raw.frame_height

  for (const detection of raw.detections) {
    const box = detection.bbox
    const x = box.x1 * scaleX
    const y = box.y1 * scaleY
    const w = (box.x2 - box.x1) * scaleX
    const h = (box.y2 - box.y1) * scaleY

    ctx.lineWidth = 2
    ctx.strokeStyle = '#13c2a3'
    ctx.fillStyle = 'rgba(19, 194, 163, 0.14)'
    ctx.strokeRect(x, y, w, h)
    ctx.fillRect(x, y, w, h)

    const label = `${detection.plate_text || 'plate'} ${(detection.confidence * 100).toFixed(0)}%`
    ctx.font = '600 13px Inter, system-ui, sans-serif'
    const labelWidth = ctx.measureText(label).width + 14
    const labelY = Math.max(6, y - 24)
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(x, labelY, labelWidth, 22)
    ctx.fillStyle = '#ffffff'
    ctx.fillText(label, x + 7, labelY + 15)
  }
}

function tick() {
  const video = videoRef.value
  if (video) {
    const current = video.currentTime || 0
    if (playbackStarted && !video.paused && current > latestProcessedTime.value - 0.18) {
      video.pause()
      isBuffering.value = true
    } else if (playbackStarted && video.paused && isBuffering.value && latestProcessedTime.value > current + RESUME_MARGIN_SECONDS) {
      isBuffering.value = false
      video.play().catch(() => {})
    }

    selectedRaw.value = pickRawForTime(current)
  }
  drawOverlay()
  animationFrame = requestAnimationFrame(tick)
}

onMounted(async () => {
  connectWs()
  await nextTick()
  tick()
  window.addEventListener('resize', drawOverlay)
})

onBeforeUnmount(() => {
  clearTimeout(reconnectTimer)
  websocket?.close()
  cancelAnimationFrame(animationFrame)
  window.removeEventListener('resize', drawOverlay)
})
</script>

<template>
  <main class="app-shell">
    <section class="video-pane">
      <div class="topbar">
        <div>
          <h1>Nomera Demo</h1>
          <p>{{ cameraLabel }} · ML {{ mlStatus }} · processed {{ processedLabel }}s</p>
        </div>
        <div class="status-row">
          <span class="pill" :class="{ ok: hasConnection }">
            <Wifi v-if="hasConnection" :size="16" />
            <WifiOff v-else :size="16" />
            {{ wsState }}
          </span>
          <span v-if="isBuffering" class="pill warn">
            <PlugZap :size="16" />
            buffering
          </span>
        </div>
      </div>

      <div class="player-wrap">
        <video
          ref="videoRef"
          class="video"
          :src="VIDEO_URL"
          muted
          playsinline
          controls
          preload="auto"
        />
        <canvas ref="canvasRef" class="overlay" />
      </div>

      <div class="controls">
        <button type="button" class="primary" :disabled="isStarting" @click="startMl">
          <CirclePlay :size="18" />
          Start ML
        </button>
        <button type="button" :disabled="isStopping" @click="stopMl">
          <Square :size="18" />
          Stop
        </button>
        <button type="button" @click="refreshStatus">
          <RefreshCcw :size="18" />
          Status
        </button>
        <button type="button" @click="pauseVideo">
          <CirclePause :size="18" />
          Pause video
        </button>
      </div>

      <p v-if="errorMessage" class="error-line">{{ errorMessage }}</p>
    </section>

    <aside class="log-pane">
      <div class="log-header">
        <h2>Detections</h2>
        <span>{{ confirmed.length }}</span>
      </div>
      <div class="log-list">
        <article v-for="item in newestConfirmed" :key="item.id" class="log-item">
          <div class="plate">{{ item.plate_text }}</div>
          <div class="meta">
            <span>{{ item.camera_role }}</span>
            <span>{{ item.timestamp_seconds.toFixed(2) }}s</span>
            <span>{{ Math.round(item.confidence * 100) }}%</span>
          </div>
          <div v-if="item.bbox" class="bbox">
            bbox {{ Math.round(item.bbox.x1) }},{{ Math.round(item.bbox.y1) }}
            → {{ Math.round(item.bbox.x2) }},{{ Math.round(item.bbox.y2) }}
          </div>
        </article>
        <div v-if="!confirmed.length" class="empty">Waiting for confirmed plates</div>
      </div>
    </aside>
  </main>
</template>
