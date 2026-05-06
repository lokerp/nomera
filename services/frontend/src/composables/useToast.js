import { reactive } from 'vue'

const state = reactive({
  items: []
})

function removeToast(id) {
  state.items = state.items.filter((item) => item.id !== id)
}

export function useToast() {
  function showToast(message, type = 'error', timeoutMs = 4200) {
    const id = `${Date.now()}-${Math.random()}`
    state.items = [...state.items, { id, message, type }]
    setTimeout(() => removeToast(id), timeoutMs)
  }

  return {
    state,
    showToast,
    removeToast
  }
}
