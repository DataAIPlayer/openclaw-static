export async function loadStats() {
  const res = await fetch('./stats.json')
  if (!res.ok) throw new Error(`加载 stats.json 失败: ${res.status}`)
  return await res.json()
}
