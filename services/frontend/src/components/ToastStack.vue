<script setup>
import { useToast } from '../composables/useToast'

const { state, removeToast } = useToast()
</script>

<template>
  <div class="toast-stack">
    <article
      v-for="item in state.items"
      :key="item.id"
      class="toast"
      :class="item.type"
      @click="removeToast(item.id)"
    >
      {{ item.message }}
    </article>
  </div>
</template>
