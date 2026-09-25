<template>
  <section class="page" data-module="blower">
    <header class="page-head">
      <div>
        <h2>鼓风机组管理</h2>
        <p class="page-desc">维护鼓风机组，围绕机组编号、机组型号、额定风量、出口压力做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记鼓风机组</button>
        <button class="btn" type="button" @click="exportRows">导出鼓风机组清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>
    <p v-if="statsError" class="error-text stats-error">
      统计卡片刷新失败：{{ statsError }}（卡片保留上次成功的数字）
      <button class="link" type="button" @click="loadSummary">重试</button>
    </p>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>机组状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit" :disabled="loading">查询</button>
      <button class="btn ghost" type="button" :disabled="loading" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td
            v-for="column in columns"
            :key="column"
            :class="{ 'cell-empty': isEmptyCell(row, column) }"
            :title="isEmptyCell(row, column) ? emptyCellHint : undefined"
          >
            {{ cellText(row, column) }}
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="acting"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="loading">
          <td :colspan="columns.length + 1" class="empty-state">鼓风机组数据加载中…</td>
        </tr>
        <tr v-else-if="listError">
          <td :colspan="columns.length + 1" class="empty-state error-state">
            <span>列表加载失败：{{ listError }}</span>
            <button class="link" type="button" @click="reload">重试</button>
          </td>
        </tr>
        <tr v-else-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyHint }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条鼓风机组记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatCard = { label: string; value: number | string }

const ENDPOINT = '/api/blower'
const columns = ["机组编号", "机组型号", "额定风量", "出口压力", "运行时长", "维护周期", "所属单元", "机组状态"]
const actions = ["启用机组", "登记维护", "停用机组"]
const statuses = ["待启用", "运行中", "维护中", "已停用"]
const DEFAULT_STATS: StatCard[] = [
  { label: "运行机组", value: 0 },
  { label: "维护中机组", value: 0 },
  { label: "今日供风量", value: 0 },
]
// 筛选字段与后端查询参数的对应关系：中文列名只用于展示，发请求时换成接口认识的参数名
const FILTER_PARAM_MAP: Record<string, string> = {
  "机组编号": 'keyword',
  "机组型号": 'model',
  "额定风量": 'airflow',
}

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<StatCard[]>(DEFAULT_STATS.map((card) => ({ ...card })))
const loading = ref(false)
const acting = ref(false)
const listError = ref('')
const statsError = ref('')
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const filterFields = columns.slice(0, 3)
const emptyCellHint = '暂无数据：该字段尚未采集，可稍后重试或联系运维补录'

const hasActiveFilter = computed(
  () => Boolean(statusFilter.value) || Object.values(filters.value).some((value) => value && value.trim()),
)

const emptyHint = computed(() =>
  hasActiveFilter.value
    ? '当前筛选条件下没有匹配的鼓风机组，可重置条件后再试'
    : '暂无鼓风机组数据，可先登记鼓风机组',
)

function buildQuery(): string {
  const params = new URLSearchParams()
  for (const [field, param] of Object.entries(FILTER_PARAM_MAP)) {
    const value = filters.value[field]?.trim()
    if (value) {
      params.set(param, value)
    }
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  return params.toString()
}

function isEmptyCell(row: Row, column: string): boolean {
  const value = row[column]
  return value === null || value === undefined || String(value).trim() === ''
}

function cellText(row: Row, column: string): string {
  return isEmptyCell(row, column) ? '—' : String(row[column])
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '鼓风机组登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  if (acting.value) {
    return
  }
  acting.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json().catch(() => null)) as {
      ok?: boolean
      message?: string
      detail?: unknown
    } | null
    const detail = typeof payload?.detail === 'string' ? payload.detail : undefined
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message ?? detail ?? '鼓风机组动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadSummary()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '鼓风机组操作失败'
  } finally {
    acting.value = false
  }
}

async function reload() {
  loading.value = true
  listError.value = ''
  errorMessage.value = ''
  const query = buildQuery()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error(`接口返回 ${response.status}，请稍后重试`)
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    rows.value = []
    total.value = 0
    listError.value = error instanceof Error ? error.message : '鼓风机组列表读取失败'
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  statsError.value = ''
  try {
    const response = await request(`${ENDPOINT}/summary`)
    if (!response.ok) {
      throw new Error(`接口返回 ${response.status}`)
    }
    const payload = (await response.json()) as { cards?: StatCard[] }
    if (Array.isArray(payload.cards) && payload.cards.length) {
      stats.value = payload.cards
    }
  } catch (error) {
    // 保留上一次成功的卡片数字，只说明原因并给出重试入口
    statsError.value = error instanceof Error ? error.message : '统计接口读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadSummary()
})
</script>
