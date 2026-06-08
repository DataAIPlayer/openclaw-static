<script setup>
defineProps({ modelValue: String })
defineEmits(['update:modelValue'])
const items = [
  { key: 'conversations', label: '对话次数' },
  { key: 'tokens', label: 'Token' },
  { key: 'skills', label: 'Skill' },
]
</script>

<template>
  <div class="group">
    <label>维度</label>
    <button
      v-for="it in items"
      :key="it.key"
      class="tab"
      :class="{ active: modelValue === it.key }"
      @click="$emit('update:modelValue', it.key)"
    >{{ it.label }}</button>
  </div>
</template>
