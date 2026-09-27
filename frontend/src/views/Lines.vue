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

interface Draft {
  planned_headway_min: number
  bunch_threshold: number
  large_threshold: number
}

const rows = ref<LineRow[]>([])
const drafts = reactive<Record<number, Draft>>({})
const errors = reactive<Record<number, string>>({})
const savedFlags = reactive<Record<number, boolean>>({})
const saving = reactive<Record<number, boolean>>({})

onMounted(load)

async function load() {
  rows.value = await api('/lines')
  for (const r of rows.value) resetDraft(r)
}

function resetDraft(r: LineRow) {
  drafts[r.id] = {
    planned_headway_min: r.planned_headway_min,
    bunch_threshold: r.bunch_threshold,
    large_threshold: r.large_threshold,
  }
}

function validate(d: Draft): string {
  const { planned_headway_min: h, bunch_threshold: b, large_threshold: l } = d
  if (!Number.isFinite(h) || !Number.isFinite(b) || !Number.isFinite(l)) return '请填写有效数字'
  if (h <= 0) return '计划发车间隔必须大于 0'
  if (b < 0 || l < 0) return '阈值不能为负数'
  if (b > l) return '串车阈值不能大于大间隔阈值'
  return ''
}

function errMsg(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e)
  try {
    const j = JSON.parse(raw)
    if (typeof j.detail === 'string') return j.detail
  } catch { /* 非 JSON 错误体 */ }
  return raw || '保存失败'
}

async function save(r: LineRow) {
  const d = drafts[r.id]
  const err = validate(d)
  if (err) {
    errors[r.id] = err
    resetDraft(r)
    return
  }
  saving[r.id] = true
  errors[r.id] = ''
  try {
    const updated: LineRow = await api(`/lines/${r.id}`, { method: 'PUT', body: JSON.stringify(d) })
    Object.assign(r, updated)
    resetDraft(r)
    savedFlags[r.id] = true
    setTimeout(() => { savedFlags[r.id] = false }, 2000)
  } catch (e) {
    errors[r.id] = errMsg(e)
    resetDraft(r)
  } finally {
    saving[r.id] = false
  }
}
</script>

<template>
  <h1>线路</h1>
  <p class="sub">运营线路与串车 / 大间隔判定阈值 · 修改保存后，重新检测即按新阈值分类</p>
  <div class="card">
    <table>
      <thead>
        <tr><th>编码</th><th>名称</th><th>计划间隔(分)</th><th>串车阈值</th><th>大间隔阈值</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.code }}</td>
          <td>{{ r.name }}</td>
          <template v-if="drafts[r.id]">
            <td><input class="num-input" type="number" min="0" step="0.5" v-model.number="drafts[r.id].planned_headway_min" /></td>
            <td><input class="num-input" type="number" min="0" step="0.5" v-model.number="drafts[r.id].bunch_threshold" /></td>
            <td><input class="num-input" type="number" min="0" step="0.5" v-model.number="drafts[r.id].large_threshold" /></td>
          </template>
          <td>
            <button class="btn" :disabled="saving[r.id]" @click="save(r)">保存</button>
            <span v-if="savedFlags[r.id]" class="save-ok">已保存</span>
            <div v-if="errors[r.id]" class="form-err">{{ errors[r.id] }}</div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
