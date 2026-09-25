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

    <div v-if="statError" class="alert alert-error" role="alert">
      <div>
        <strong>统计卡片读取失败</strong>
        <p>{{ statError }}<template v-if="statStale">卡片当前展示的是刷新前保留的统计数字。</template></p>
      </div>
      <button class="btn" type="button" @click="loadStats">重试统计</button>
    </div>

    <div class="stat-row">
      <button
        v-for="item in statsCards"
        :key="item.label"
        type="button"
        class="stat-card"
        :class="{ 'stat-card--active': item.match && filters.status === item.match }"
        :title="item.match ? `点击按「${item.match}」筛选列表` : undefined"
        @click="item.match && filterByStatus(item.match)"
      >
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
        <span v-if="item.note" class="stat-note">{{ item.note }}</span>
      </button>
    </div>

    <form class="filter-bar" @submit.prevent="runQuery">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>机组状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="listError" class="alert alert-error" role="alert">
      <div>
        <strong>鼓风机组列表读取失败</strong>
        <p>{{ listError }}<template v-if="rows.length">下表当前展示的是刷新前保留的数据，可能不是最新结果。</template></p>
      </div>
      <button class="btn" type="button" @click="reload">重试加载</button>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="hasValue(row[column])">{{ row[column] }}</span>
            <span v-else class="cell-empty" :title="emptyHint(column)">暂未填报</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!loading && !rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            <template v-if="listError">列表加载失败且本地没有可展示的保留数据，请点击上方「重试加载」</template>
            <template v-else-if="hasActiveFilters">当前筛选条件下没有匹配的鼓风机组记录，可调整筛选条件或点击「重置条件」</template>
            <template v-else>暂无鼓风机组数据，可先登记鼓风机组</template>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条鼓风机组记录<span v-if="listStale" class="stale-tag">保留数据</span></span>
      <span v-if="actionMessage" class="success-text">{{ actionMessage }}</span>
      <span v-if="actionError" class="error-text">{{ actionError }}</span>
    </footer>

    <div v-if="createOpen" class="modal-mask" @click.self="closeCreate">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="blower-create-title">
        <h3 id="blower-create-title">登记鼓风机组</h3>
        <form class="modal-form" @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field.key" class="form-item">
            <span>{{ field.label }}<em v-if="field.required">*</em></span>
            <input v-model="form[field.key]" :placeholder="`请输入${field.label}`" />
          </label>
          <p v-if="createError" class="error-text form-error">{{ createError }}</p>
          <div class="modal-actions">
            <button class="btn primary" type="submit" :disabled="submitting">
              {{ submitting ? '提交中…' : '提交登记' }}
            </button>
            <button class="btn ghost" type="button" :disabled="submitting" @click="closeCreate">取消</button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Filters = Record<string, string>

interface StatPayload {
  运行机组: number
  维护中机组: number
  今日供风量: number | null
}

interface ActionPayload {
  ok: boolean
  message: string
}

interface StatsCache {
  stats: StatPayload
  savedAt: string
}

interface ListCache {
  items: Row[]
  total: number
  savedAt: string
}

const ENDPOINT = '/api/blower'
const STATS_CACHE_KEY = 'blower:stats:v1'
const LIST_CACHE_KEY = 'blower:list:v1'
const columns = ["机组编号", "机组型号", "额定风量", "出口压力", "运行时长", "维护周期", "所属单元", "机组状态"]
const filterFields = ["机组编号", "机组型号", "额定风量"]
const actions = ["启用机组", "登记维护", "停用机组"]
const statuses = ["待启用", "运行中", "维护中", "已停用"]
const createFields = [
  { key: '机组编号', label: '机组编号', required: true },
  { key: '机组型号', label: '机组型号', required: true },
  { key: '额定风量', label: '额定风量', required: true },
  { key: '出口压力', label: '出口压力', required: false },
  { key: '运行时长', label: '运行时长', required: false },
  { key: '维护周期', label: '维护周期', required: false },
  { key: '所属单元', label: '所属单元', required: false },
] as const

const rows = ref<Row[]>([])
const total = ref(0)
const loading = ref(false)
const listError = ref('')
const listStale = ref(false)
const actionMessage = ref('')
const actionError = ref('')
const filters = ref<Filters>({ 机组编号: '', 机组型号: '', 额定风量: '', status: '' })

const statRaw = ref<StatPayload | null>(null)
const statError = ref('')
const statStale = ref(false)

const createOpen = ref(false)
const submitting = ref(false)
const createError = ref('')
const form = ref<Record<string, string>>({})

function readCache<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function writeCache(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 本地存储不可用（隐私模式等）时不阻断主流程，只是刷新后无法保留数字。
  }
}

// 先读本地保留值，保证刷新页面瞬间卡片和列表仍有上次的数字，再请求最新数据覆盖。
const cachedStats = readCache<StatsCache>(STATS_CACHE_KEY)
if (cachedStats?.stats) {
  statRaw.value = cachedStats.stats
}
const cachedLists = readCache<Record<string, ListCache>>(LIST_CACHE_KEY) ?? {}
const cachedDefault = cachedLists['']
if (cachedDefault) {
  rows.value = cachedDefault.items
  total.value = cachedDefault.total
}

const statsCards = computed(() => {
  const stats = statRaw.value
  const airflow = stats?.今日供风量 ?? null
  return [
    { label: '运行机组', value: stats ? stats.运行机组 : '—', note: '', match: '运行中' as const },
    { label: '维护中机组', value: stats ? stats.维护中机组 : '—', note: '', match: '维护中' as const },
    {
      label: '今日供风量',
      value: stats ? (airflow === null ? '暂无数据' : airflow) : '—',
      note: stats && airflow === null ? '运行中机组均未填报额定风量，暂无统计值' : '',
      match: null,
    },
  ]
})

const hasActiveFilters = computed(() =>
  Object.values(filters.value).some((value) => value.trim() !== ''),
)

function hasValue(value: unknown): boolean {
  return value !== null && value !== undefined && String(value).trim() !== ''
}

function emptyHint(column: string): string {
  return `该机组尚未填报「${column}」，请在机组台账中补录后再查看`
}

function explain(error: unknown): string {
  return error instanceof Error ? error.message : '请求失败，请稍后重试'
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const data = (await response.json()) as { message?: unknown; detail?: unknown }
    if (typeof data.message === 'string' && data.message) {
      return data.message
    }
    if (typeof data.detail === 'string' && data.detail) {
      return data.detail
    }
  } catch {
    // 错误体不是 JSON 时退回通用说明。
  }
  return `${fallback}（接口返回 ${response.status}），请检查后端服务后重试`
}

function buildQuery(): string {
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = filters.value[field].trim()
    if (value) {
      params.set(field, value)
    }
  }
  if (filters.value.status) {
    params.set('status', filters.value.status)
  }
  return params.toString()
}

async function loadStats() {
  statError.value = ''
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      throw new Error(await readError(response, '鼓风机组统计读取失败'))
    }
    statRaw.value = (await response.json()) as StatPayload
    statStale.value = false
    writeCache(STATS_CACHE_KEY, { stats: statRaw.value, savedAt: new Date().toISOString() })
  } catch (error) {
    // 失败时保留刷新前/上次成功的统计数字，只把原因说清楚并给重试入口。
    if (!statRaw.value && cachedStats?.stats) {
      statRaw.value = cachedStats.stats
    }
    statStale.value = statRaw.value !== null
    statError.value = explain(error)
  }
}

async function reload() {
  // 注意：不在这里清空 actionMessage/actionError——动作成功后紧接着 reload，
  // 清掉会让「已登记维护」这类反馈一闪而过。
  listError.value = ''
  listStale.value = false
  loading.value = true
  const query = buildQuery()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error(await readError(response, '鼓风机组列表读取失败'))
    }
    const payload = (await response.json()) as { items?: Row[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    cachedLists[query] = { items: rows.value, total: total.value, savedAt: new Date().toISOString() }
    writeCache(LIST_CACHE_KEY, cachedLists)
  } catch (error) {
    listError.value = explain(error)
    const fallback = cachedLists[query]
    if (fallback) {
      rows.value = fallback.items
      total.value = fallback.total
      listStale.value = true
    }
  } finally {
    loading.value = false
  }
  void loadStats()
}

function runQuery() {
  actionError.value = ''
  actionMessage.value = ''
  void reload()
}

function resetFilters() {
  actionError.value = ''
  actionMessage.value = ''
  filters.value = { 机组编号: '', 机组型号: '', 额定风量: '', status: '' }
  void reload()
}

function filterByStatus(status: string) {
  actionError.value = ''
  actionMessage.value = ''
  filters.value.status = filters.value.status === status ? '' : status
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createError.value = ''
  form.value = Object.fromEntries(createFields.map((field) => [field.key, '']))
  createOpen.value = true
}

function closeCreate() {
  if (submitting.value) {
    return
  }
  createOpen.value = false
  createError.value = ''
}

async function submitCreate() {
  if (submitting.value) {
    return
  }
  createError.value = ''
  submitting.value = true
  try {
    const values: Record<string, string> = {}
    for (const field of createFields) {
      const value = form.value[field.key]?.trim()
      if (value) {
        values[field.key] = value
      }
    }
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = (await response.json().catch(() => null)) as ActionPayload | null
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '鼓风机组登记失败，请稍后重试')
    }
    createOpen.value = false
    actionMessage.value = payload.message
    await reload()
  } catch (error) {
    createError.value = explain(error)
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string, row: Row) {
  actionError.value = ''
  actionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json().catch(() => null)) as ActionPayload | null
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '鼓风机组动作未生效，请稍后重试')
    }
    actionMessage.value = payload.message
    await reload()
  } catch (error) {
    actionError.value = explain(error)
  }
}

onMounted(reload)
</script>

<style scoped>
.stat-card {
  text-align: left;
  font: inherit;
  cursor: default;
}
.stat-card[title] {
  cursor: pointer;
}
.stat-card--active {
  border-color: var(--brand);
  box-shadow: 0 0 0 1px var(--brand) inset;
}
.stat-note {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}
.cell-empty {
  color: var(--muted);
  font-size: 12px;
}
.alert {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  border: 1px solid #f0a8a0;
  background: #fef3f2;
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
}
.alert p {
  margin: 2px 0 0;
  font-size: 12px;
  color: #7a271a;
}
.stale-tag {
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 4px;
  background: #fef3c7;
  color: #92400e;
}
.success-text {
  color: #067647;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  width: 520px;
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
}
.modal h3 {
  margin: 0 0 12px;
}
.modal-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.form-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 2px;
}
.form-item em {
  color: #b42318;
  font-style: normal;
  margin-left: 2px;
}
.form-item input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
}
.form-error {
  margin: 0;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
