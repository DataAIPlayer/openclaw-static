<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  bucket: { type: Object, default: null },  // 单个时间桶 {users, skills_ranking}
  metric: { type: String, required: true }, // conversations | tokens | skills
  desc: { type: Boolean, default: true },   // 降序
})

const expanded = ref(new Set())
function toggle(name) {
  const s = new Set(expanded.value)
  s.has(name) ? s.delete(name) : s.add(name)
  expanded.value = s
}

const isSkill = computed(() => props.metric === 'skills')

// 用户维度(对话/token): 取 users，按选中数值排序
const userRows = computed(() => {
  const users = props.bucket?.users ?? []
  const val = (u) => props.metric === 'tokens' ? u.tokens.total : u.conversations
  return [...users].sort((a, b) => props.desc ? val(b) - val(a) : val(a) - val(b))
})

// skill 维度: 取 skills_ranking，按 count 排序
const skillRows = computed(() => {
  const ranking = props.bucket?.skills_ranking ?? []
  return [...ranking].sort((a, b) => props.desc ? b.count - a.count : a.count - b.count)
})

function fmt(n) { return (n ?? 0).toLocaleString() }
</script>

<template>
  <div v-if="!bucket" class="empty">该周期暂无数据</div>

  <table v-else-if="!isSkill">
    <thead>
      <tr>
        <th>#</th>
        <th>用户</th>
        <th class="num">对话次数</th>
        <th class="num">Token</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(u, i) in userRows" :key="u.user">
        <td>{{ i + 1 }}</td>
        <td>{{ u.user }}</td>
        <td class="num">{{ fmt(u.conversations) }}</td>
        <td class="num">{{ fmt(u.tokens.total) }}</td>
      </tr>
      <tr v-if="userRows.length === 0"><td colspan="4" class="empty">无数据</td></tr>
    </tbody>
  </table>

  <table v-else>
    <thead>
      <tr>
        <th>#</th>
        <th>Skill</th>
        <th class="num">使用次数</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      <template v-for="(s, i) in skillRows" :key="s.name">
        <tr class="skill-row" @click="toggle(s.name)">
          <td>{{ i + 1 }}</td>
          <td>{{ s.name }}</td>
          <td class="num">{{ fmt(s.count) }}</td>
          <td>{{ expanded.has(s.name) ? '▾' : '▸' }}</td>
        </tr>
        <template v-if="expanded.has(s.name)">
          <tr v-for="bu in s.by_user" :key="s.name + '|' + bu.user" class="detail">
            <td></td>
            <td>{{ bu.user }}</td>
            <td class="num">{{ fmt(bu.count) }}</td>
            <td></td>
          </tr>
        </template>
      </template>
      <tr v-if="skillRows.length === 0"><td colspan="4" class="empty">无 skill 数据</td></tr>
    </tbody>
  </table>
</template>
