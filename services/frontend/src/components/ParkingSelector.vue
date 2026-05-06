<script setup>
defineProps({
  parkingLots: { type: Array, required: true },
  selectedParkingLotId: { type: String, default: '' }
})

const emit = defineEmits(['change'])
</script>

<template>
  <label class="inline-field">
    Парковка
    <select :value="selectedParkingLotId" @change="emit('change', $event.target.value)">
      <option v-for="item in parkingLots" :key="item.id" :value="item.id">{{ item.name }}</option>
    </select>
  </label>
</template>
