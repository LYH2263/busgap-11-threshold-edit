<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'

interface LineRow {
  id: number
  code: string
  name: string
  planned_headway_min: number
  bunch_threshold: number
  large_threshold: number
}

const rows = ref<LineRow[]>([])
const drafts = reactive<Record<number, { planned_headway_min: number; bunch_threshold: number; large_threshold: number }>>({})
const saving = reactive<Record<number, boolean>>({})
const messages = reactive<Record<number, { ok: boolean; text: string }>>({})

function resetDraft(r: LineRow) {
  drafts[r.id] = {
    planned_headway_min: r.planned_headway_min,
    bunch_threshold: r.bunch_threshold,
    large_threshold: r.large_threshold,
  }
}

onMounted(async () => {
  rows.value = await api('/lines')
  rows.value.forEach(resetDraft)
})

function parseError(e: any): string {
  try {
    const j = JSON.parse(e?.message ?? '')
    if (typeof j.detail === 'string') return j.detail
  } catch { /* 非 JSON 错误体 */ }
  return '保存失败，请检查输入'
}

async function save(r: LineRow) {
  saving[r.id] = true
  delete messages[r.id]
  const d = drafts[r.id]
  try {
    const updated: LineRow = await api(`/lines/${r.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        planned_headway_min: Number(d.planned_headway_min),
        bunch_threshold: Number(d.bunch_threshold),
        large_threshold: Number(d.large_threshold),
      }),
    })
    const i = rows.value.findIndex(x => x.id === r.id)
    if (i >= 0) rows.value[i] = updated
    resetDraft(updated)
    messages[r.id] = { ok: true, text: '已保存' }
  } catch (e: any) {
    resetDraft(r) // 拒绝保存时页上数字保持改前
    messages[r.id] = { ok: false, text: parseError(e) }
  } finally {
    saving[r.id] = false
  }
}
</script>
<template>
  <h1>线路</h1>
  <p class="sub">运营线路与串车 / 大间隔判定阈值 · 修改保存后重新检测即按新阈值分类</p>
  <div class="card">
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>计划间隔(分)</th><th>串车阈值</th><th>大间隔阈值</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.code }}</td>
          <td>{{ r.name }}</td>
          <template v-if="drafts[r.id]">
            <td><input class="num-input" type="number" step="0.5" v-model.number="drafts[r.id].planned_headway_min" /></td>
            <td><input class="num-input" type="number" step="0.5" v-model.number="drafts[r.id].bunch_threshold" /></td>
            <td><input class="num-input" type="number" step="0.5" v-model.number="drafts[r.id].large_threshold" /></td>
          </template>
          <td>
            <button class="btn" :disabled="saving[r.id]" @click="save(r)">保存</button>
            <span v-if="messages[r.id]" class="row-msg" :class="messages[r.id].ok ? 'ok' : 'err'">
              {{ messages[r.id].text }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
