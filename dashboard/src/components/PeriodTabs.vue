<script setup>
defineProps({ modelValue: String })
defineEmits(['update:modelValue'])
const items = [
  { key: 'day', label: '日' },
  { key: 'week', label: '周' },
  { key: 'month', label: '月' },
]
</script>

<template>
  <div class="group">
    <label>周期</label>
    <button
      v-for="it in items"
      :key="it.key"
      class="tab"
      :class="{ active: modelValue === it.key }"
      @click="$emit('update:modelValue', it.key)"
    >{{ it.label }}</button>
  </div>
</template>
