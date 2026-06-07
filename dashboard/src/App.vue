<script setup>
import { ref, computed, onMounted } from 'vue'
import { loadStats } from './api.js'
import PeriodTabs from './components/PeriodTabs.vue'
import MetricTabs from './components/MetricTabs.vue'
import RankingTable from './components/RankingTable.vue'

const stats = ref(null)
const error = ref(null)
const period = ref('day')        // day | week | month
const metric = ref('conversations')
const desc = ref(true)
const bucketKey = ref(null)

onMounted(async () => {
  try {
    stats.value = await loadStats()
    pickDefaultBucket()
  } catch (e) {
    error.value = e.message
  }
})

const buckets = computed(() => stats.value?.periods?.[period.value] ?? [])

function pickDefaultBucket() {
  const list = buckets.value
  // 默认选最近一个(bucket 已按时间升序，取最后)
  bucketKey.value = list.length ? list[list.length - 1].bucket : null
}

function onPeriodChange(p) {
  period.value = p
  pickDefaultBucket()
}

const currentBucket = computed(() =>
  buckets.value.find((b) => b.bucket === bucketKey.value) ?? null,
)
</script>

<template>
  <h1>Openclaw 使用看板</h1>
  <div class="meta" v-if="stats">生成时间：{{ stats.generated_at }}</div>

  <div v-if="error" class="empty">加载失败：{{ error }}</div>

  <template v-else-if="stats">
    <div class="controls">
      <PeriodTabs :model-value="period" @update:model-value="onPeriodChange" />
      <div class="group">
        <label>时间桶</label>
        <select v-model="bucketKey">
          <option v-for="b in buckets" :key="b.bucket" :value="b.bucket">
            {{ b.label }}
          </option>
        </select>
      </div>
      <MetricTabs v-model="metric" />
      <div class="group">
        <label>排序</label>
        <button class="tab" @click="desc = !desc">{{ desc ? '↓ 降序' : '↑ 升序' }}</button>
      </div>
    </div>

    <RankingTable :bucket="currentBucket" :metric="metric" :desc="desc" />
  </template>

  <div v-else class="empty">加载中…</div>
</template>
