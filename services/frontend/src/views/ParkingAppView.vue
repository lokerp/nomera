<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { API_BASE, apiRequest } from '../api/client'
import CamerasPanel from '../components/CamerasPanel.vue'
import LogsPanel from '../components/LogsPanel.vue'
import PlatesPanel from '../components/PlatesPanel.vue'
import ToastStack from '../components/ToastStack.vue'
import UsersPanel from '../components/UsersPanel.vue'
import { useAuth } from '../composables/useAuth'
import { useToast } from '../composables/useToast'

const tabs = ['cameras', 'plates', 'logs', 'users']
const activeTab = ref('cameras')
const error = ref('')
const loading = ref(false)

const parkingLots = ref([])
const selectedParkingLotId = ref('')
const cameras = ref([])
const pendingRequests = ref([])
const allowedPlates = ref([])
const scanLogs = ref([])
const stats = ref({})
const users = ref([])
const logsCameraFilter = ref('')
let refreshTimer = null

const router = useRouter()
const { state, isAdmin, clearSession } = useAuth()
const { showToast } = useToast()

const visibleTabs = computed(() => (isAdmin.value ? tabs : tabs.filter((tab) => tab !== 'users')))
const roleLabel = computed(() => (state.user?.role === 'admin' ? 'Администратор' : 'Охранник'))
const activeTabHint = computed(
  () =>
    ({
      cameras: 'Парковки, камеры и видеопотоки',
      plates: 'Заявки и постоянные допуски',
      logs: 'События распознавания и аналитика',
      users: 'Учетные записи и доступы'
    })[activeTab.value]
)
const selectedParkingName = computed(
  () => parkingLots.value.find((item) => item.id === selectedParkingLotId.value)?.name || 'Парковка не выбрана'
)
const tabLabels = {
  cameras: 'Парковки',
  plates: 'Допуски и заявки',
  logs: 'История и аналитика',
  users: 'Пользователи'
}

async function loadParkingLots() {
  parkingLots.value = await apiRequest('/api/parking-lots')
  const exists = parkingLots.value.some((item) => item.id === selectedParkingLotId.value)
  if ((!selectedParkingLotId.value || !exists) && parkingLots.value.length) {
    selectedParkingLotId.value = parkingLots.value[0].id
  } else if (!parkingLots.value.length) {
    selectedParkingLotId.value = ''
  }
}

async function loadCameras() {
  if (!selectedParkingLotId.value) {
    cameras.value = []
    return
  }
  cameras.value = await apiRequest(`/api/cameras?parking_lot_id=${selectedParkingLotId.value}`)
}

async function loadPlatesAndRequests() {
  if (!selectedParkingLotId.value) {
    allowedPlates.value = []
    pendingRequests.value = []
    return
  }
  allowedPlates.value = await apiRequest(`/api/allowed-plates?parking_lot_id=${selectedParkingLotId.value}`)
  pendingRequests.value = await apiRequest(
    `/api/access-requests?parking_lot_id=${selectedParkingLotId.value}&status_filter=pending`
  )
}

async function loadLogs() {
  if (!selectedParkingLotId.value) {
    scanLogs.value = []
    stats.value = {}
    return
  }
  const query = new URLSearchParams({ parking_lot_id: selectedParkingLotId.value })
  if (logsCameraFilter.value) {
    query.set('camera_id', logsCameraFilter.value)
  }
  scanLogs.value = await apiRequest(`/api/scan-logs?${query.toString()}`)
  stats.value = await apiRequest(`/api/scan-logs/analytics?parking_lot_id=${selectedParkingLotId.value}`)
}

async function loadUsers() {
  if (!isAdmin.value) return
  users.value = await apiRequest('/api/users')
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    await loadParkingLots()
    await Promise.all([loadCameras(), loadPlatesAndRequests(), loadLogs(), loadUsers()])
  } catch (err) {
    error.value = 'Не удалось загрузить данные. Проверьте подключение и права доступа.'
    showToast(err.message || error.value)
  } finally {
    loading.value = false
  }
}

async function refreshActiveTab() {
  try {
    await loadParkingLots()
    if (activeTab.value === 'cameras') {
      await loadCameras()
      return
    }
    if (activeTab.value === 'plates') {
      await Promise.all([loadPlatesAndRequests(), loadCameras()])
      return
    }
    if (activeTab.value === 'logs') {
      await Promise.all([loadLogs(), loadCameras()])
      return
    }
    if (activeTab.value === 'users' && isAdmin.value) {
      await Promise.all([loadUsers(), loadParkingLots()])
    }
  } catch (err) {
    showToast(err.message || 'Не удалось обновить данные')
  }
}

async function createCamera(payload) {
  try {
    let finalPayload = { ...payload }
    if (payload.source_type === 'mp4' && payload.mp4_file) {
      const formData = new FormData()
      formData.append('file', payload.mp4_file)
      const uploadResponse = await apiRequest('/api/cameras/upload-video', {
        method: 'POST',
        body: formData,
        headers: {}
      })
      finalPayload.stream_url = `${API_BASE}${uploadResponse.video_url}${payload.mp4_loop ? '?loop=1' : ''}`
    }
    const requestPayload = {
      id: finalPayload.id,
      name: finalPayload.name,
      parking_lot_id: finalPayload.parking_lot_id,
      stream_url: finalPayload.stream_url
    }
    await apiRequest('/api/cameras', { method: 'POST', body: JSON.stringify(requestPayload) })
    await loadCameras()
    showToast('Камера добавлена', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось добавить камеру')
  }
}

async function updateCamera(cameraId, payload, done) {
  try {
    let finalPayload = { ...payload }
    if (payload.source_type === 'mp4' && payload.mp4_file) {
      const formData = new FormData()
      formData.append('file', payload.mp4_file)
      const uploadResponse = await apiRequest('/api/cameras/upload-video', {
        method: 'POST',
        body: formData,
        headers: {}
      })
      finalPayload.stream_url = `${API_BASE}${uploadResponse.video_url}${payload.mp4_loop ? '?loop=1' : ''}`
    }
    const requestPayload = {
      id: finalPayload.id,
      name: finalPayload.name,
      parking_lot_id: finalPayload.parking_lot_id,
      stream_url: finalPayload.stream_url
    }
    await apiRequest(`/api/cameras/${cameraId}`, { method: 'PUT', body: JSON.stringify(requestPayload) })
    await loadCameras()
    done?.()
    showToast('Камера обновлена', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось обновить камеру')
  }
}

async function deleteCamera(cameraId) {
  try {
    await apiRequest(`/api/cameras/${cameraId}`, { method: 'DELETE' })
    await loadCameras()
    showToast('Камера удалена', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось удалить камеру')
  }
}

async function createParkingLot(payload, done) {
  try {
    const created = await apiRequest('/api/parking-lots', { method: 'POST', body: JSON.stringify(payload) })
    await loadParkingLots()
    selectedParkingLotId.value = created.id
    done?.()
    showToast('Парковка добавлена', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось добавить парковку')
  }
}

async function updateParkingLot(parkingLotId, payload, done) {
  try {
    await apiRequest(`/api/parking-lots/${parkingLotId}`, { method: 'PUT', body: JSON.stringify(payload) })
    await loadParkingLots()
    done?.()
    showToast('Парковка обновлена', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось обновить парковку')
  }
}

async function deleteParkingLot(parkingLotId) {
  try {
    await apiRequest(`/api/parking-lots/${parkingLotId}`, { method: 'DELETE' })
    await loadParkingLots()
    if (selectedParkingLotId.value === parkingLotId) {
      selectedParkingLotId.value = parkingLots.value[0]?.id || ''
    }
    showToast('Парковка удалена', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось удалить парковку')
  }
}

async function createAllowedPlate(payload) {
  try {
    payload.parking_lot_id = selectedParkingLotId.value
    await apiRequest('/api/allowed-plates', { method: 'POST', body: JSON.stringify(payload) })
    await loadPlatesAndRequests()
    showToast('Допуск добавлен', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось добавить допуск')
  }
}

async function updateAllowedPlate(id, payload, done) {
  try {
    payload.parking_lot_id = selectedParkingLotId.value
    await apiRequest(`/api/allowed-plates/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
    await loadPlatesAndRequests()
    done?.()
    showToast('Допуск обновлен', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось обновить допуск')
  }
}

async function deleteAllowedPlate(id) {
  try {
    await apiRequest(`/api/allowed-plates/${id}`, { method: 'DELETE' })
    await loadPlatesAndRequests()
    showToast('Допуск удален', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось удалить допуск')
  }
}

async function approveRequest(id) {
  try {
    await apiRequest(`/api/access-requests/${id}/approve`, { method: 'POST' })
    await loadPlatesAndRequests()
    showToast('Заявка одобрена', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось одобрить заявку')
  }
}

async function rejectRequest(id) {
  try {
    await apiRequest(`/api/access-requests/${id}/reject`, { method: 'POST' })
    await loadPlatesAndRequests()
    showToast('Заявка отклонена', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось отклонить заявку')
  }
}

async function createAccessRequest(payload) {
  try {
    await apiRequest('/api/public/requests', { method: 'POST', body: JSON.stringify(payload) })
    await loadPlatesAndRequests()
    showToast('Заявка отправлена', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось отправить заявку')
  }
}

async function updateAccessRequest(id, payload, done) {
  try {
    await apiRequest(`/api/access-requests/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
    await loadPlatesAndRequests()
    done?.()
    showToast('Заявка обновлена', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось обновить заявку')
  }
}

async function createUser(payload) {
  try {
    await apiRequest('/api/users', { method: 'POST', body: JSON.stringify(payload) })
    await loadUsers()
    showToast('Пользователь создан', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось создать пользователя')
  }
}

async function deleteUser(userId) {
  try {
    await apiRequest(`/api/users/${userId}`, { method: 'DELETE' })
    await loadUsers()
    showToast('Пользователь удален', 'success')
  } catch (err) {
    showToast(err.message || 'Не удалось удалить пользователя')
  }
}

function logout() {
  clearSession()
  router.push({ name: 'login' })
}

async function manualRefresh() {
  await refreshActiveTab()
}

function handleConfirmedDetection(payload) {
  const currentParking = selectedParkingLotId.value
  if (activeTab.value !== 'logs' || !currentParking) return
  if (payload.parking_lot_id !== currentParking) return
  if (logsCameraFilter.value && payload.camera_id !== logsCameraFilter.value) return

  const nextItem = {
    id: payload.scan_log_id || payload.id || `${payload.camera_id}-${payload.timestamp_seconds}`,
    parking_lot_id: payload.parking_lot_id,
    camera_id: payload.camera_id,
    plate_number: payload.plate_text,
    photo_url: payload.photo_url || '',
    frame_width: payload.frame_width || 0,
    frame_height: payload.frame_height || 0,
    bbox_x1: payload.bbox?.x1 ?? null,
    bbox_y1: payload.bbox?.y1 ?? null,
    bbox_x2: payload.bbox?.x2 ?? null,
    bbox_y2: payload.bbox?.y2 ?? null,
    bbox_confidence: payload.bbox?.confidence ?? null,
    timestamp: payload.timestamp || new Date().toISOString()
  }
  scanLogs.value = [nextItem, ...scanLogs.value.filter((item) => item.id !== nextItem.id)].slice(0, 200)
  stats.value = {
    ...stats.value,
    recognitions_today: (stats.value.recognitions_today || 0) + 1
  }
}

watch(selectedParkingLotId, async () => {
  await Promise.all([loadCameras(), loadPlatesAndRequests(), loadLogs()])
})
watch(logsCameraFilter, async () => {
  await loadLogs()
})

onMounted(loadData)
onMounted(() => {
  refreshTimer = setInterval(() => {
    refreshActiveTab()
  }, 5000)
})
onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
  <main class="ops-shell">
    <header class="ops-topbar">
      <div class="ops-brand">
        <p class="ops-kicker">Nomera</p>
        <h1>Операционная панель парковки</h1>
      </div>
      <div class="ops-toolbar">
        <div class="ops-context">
          <p>{{ state.user?.username }}</p>
          <span>{{ roleLabel }}</span>
        </div>
        <button type="button" @click="manualRefresh">Обновить</button>
        <button type="button" class="danger" @click="logout">Выйти</button>
      </div>
    </header>

    <aside class="ops-rail">
      <p class="ops-rail-title">Разделы</p>
      <nav class="ops-tabs">
        <button
          v-for="tab in visibleTabs"
          :key="tab"
          :class="{ active: tab === activeTab }"
          type="button"
          :aria-current="tab === activeTab ? 'page' : undefined"
          @click="activeTab = tab"
        >
          {{ tabLabels[tab] }}
        </button>
      </nav>
      <div class="ops-active-summary">
        <p class="ops-active-label">{{ tabLabels[activeTab] }}</p>
        <p class="ops-active-text">{{ activeTabHint }}</p>
      </div>
    </aside>

    <section class="ops-main">
      <div class="ops-status-row">
        <div class="ops-chip">
          <span>Текущая парковка</span>
          <strong>{{ selectedParkingName }}</strong>
        </div>
        <p v-if="loading" class="muted" aria-live="polite">Синхронизация данных...</p>
      </div>

      <p v-if="error" class="error ops-error" role="alert" aria-live="polite">{{ error }}</p>

      <CamerasPanel
        v-if="activeTab === 'cameras'"
        :parking-lots="parkingLots"
        :cameras="cameras"
        :is-admin="isAdmin"
        :selected-parking-lot-id="selectedParkingLotId"
        @select-parking="selectedParkingLotId = $event"
        @create-parking="createParkingLot"
        @update-parking="updateParkingLot"
        @delete-parking="deleteParkingLot"
        @save-camera="createCamera"
        @update-camera="updateCamera"
        @delete-camera="deleteCamera"
      />
      <PlatesPanel
        v-if="activeTab === 'plates'"
        :pending-requests="pendingRequests"
        :allowed-plates="allowedPlates"
        :selected-parking-lot-id="selectedParkingLotId"
        @approve="approveRequest"
        @reject="rejectRequest"
        @save-plate="createAllowedPlate"
        @update-plate="updateAllowedPlate"
        @delete-plate="deleteAllowedPlate"
        @create-request="createAccessRequest"
        @update-request="updateAccessRequest"
      />
      <LogsPanel
        v-if="activeTab === 'logs'"
        :logs="scanLogs"
        :stats="stats"
        :cameras="cameras"
        :token="state.token"
        :selected-camera-id="logsCameraFilter"
        @change-camera-filter="logsCameraFilter = $event"
        @confirmed-detection="handleConfirmedDetection"
      />
      <UsersPanel
        v-if="activeTab === 'users' && isAdmin"
        :users="users"
        :parking-lots="parkingLots"
        @save-user="createUser"
        @delete-user="deleteUser"
      />
    </section>
    <ToastStack />
  </main>
</template>
