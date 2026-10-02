<template>
  <section class="page" data-module="lightningprot">
    <header class="page-head">
      <div>
        <h2>防雷接地管理</h2>
        <p class="page-desc">维护防雷装置台账，接地电阻复测按周期排期；登记结果与浪涌模块更换后，装置状态与复测队列同步更新。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn primary" to="/lightningprot/queue">打开复测队列</RouterLink>
        <button class="btn" type="button" @click="exportRows">导出防雷接地清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>装置状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '装置状态'">
              <span :class="['tag', stateClass(row['装置状态'])]">{{ row['装置状态'] }}</span>
            </template>
            <template v-else-if="column === '下次复测日'">
              {{ row['下次复测日'] || '—' }}
              <span :class="['sub-text', overdue(row) ? 'bad-text' : '']">{{ daysLabel(row.距复测天数) }}</span>
            </template>
            <template v-else-if="column === '队列状态'">
              <span v-if="row.in_queue" :class="['tag', queueClass(row.队列状态)]">{{ row.队列状态 }}</span>
              <span v-else class="tag tag-ok">合格·未到期</span>
            </template>
            <template v-else-if="column === '接地电阻'">
              {{ row.接地电阻 === null ? '—' : `${row.接地电阻}Ω` }}
            </template>
            <template v-else>{{ cellText(row, column) }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openRetest(row)">登记复测</button>
            <button class="link" type="button" @click="openSpd(row)">换SPD</button>
            <button class="link" type="button" @click="openHistory(row)">档案</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无防雷接地数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条防雷接地记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <RetestDialog
      :device="activeDialog === 'retest' ? activeDevice : null"
      :settings="settings"
      :default-tester="store.operator"
      @close="closeDialog"
      @saved="onSaved"
    />
    <SpdDialog
      :device="activeDialog === 'spd' ? activeDevice : null"
      :settings="settings"
      :default-tester="store.operator"
      @close="closeDialog"
      @saved="onSaved"
    />
    <HistoryDrawer :device="historyDevice" @close="historyDevice = null" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import RetestDialog from './components/RetestDialog.vue'
import SpdDialog from './components/SpdDialog.vue'
import HistoryDrawer from './components/HistoryDrawer.vue'
import { daysLabel, queueClass, stateClass, type QueueItem, type QueueSettings } from './queue-ui'

type Row = QueueItem
type TextColumn = '装置编号' | '所属站点' | '防雷模块' | '浪涌保护' | '上次测试' | '测试人员'

const ENDPOINT = '/api/lightningprot'
const columns = [
  '装置编号', '所属站点', '接地电阻', '防雷模块', '浪涌保护',
  '上次测试', '测试人员', '装置状态', '下次复测日', '队列状态',
] as const
const statuses = ['合格', '电阻超标', '模块劣化', '已更换']

const store = useSessionStore()
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({ 装置编号: '', 所属站点: '' })
const filterFields = ['装置编号', '所属站点']
const statusFilter = ref('')
const settings = ref<QueueSettings>({ cycle_months: 12, warn_days: 30, resistance_limit: 10 })

const activeDevice = ref<QueueItem | null>(null)
const activeDialog = ref<'retest' | 'spd' | ''>('')
const historyDevice = ref<QueueItem | null>(null)

function overdue(row: Row): boolean {
  return row.距复测天数 !== null && row.距复测天数 < 0
}

function cellText(row: Row, column: string): string {
  const textColumns: TextColumn[] = ['装置编号', '所属站点', '防雷模块', '浪涌保护', '上次测试', '测试人员']
  const key = column as TextColumn
  return (textColumns.includes(key) ? row[key] : '') || '—'
}

const stats = computed(() => [
  { label: '合格装置', value: rows.value.filter((row) => row.装置状态 === '合格').length },
  { label: '超标装置', value: rows.value.filter((row) => row.装置状态 === '电阻超标').length },
  { label: '劣化/待换', value: rows.value.filter((row) => row.装置状态 === '模块劣化').length },
  { label: '在复测队列', value: rows.value.filter((row) => row.in_queue).length },
])

function resetFilters() {
  filters.value = { 装置编号: '', 所属站点: '' }
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openRetest(row: Row) {
  activeDevice.value = row
  activeDialog.value = 'retest'
}

function openSpd(row: Row) {
  activeDevice.value = row
  activeDialog.value = 'spd'
}

function openHistory(row: Row) {
  historyDevice.value = row
}

function closeDialog() {
  activeDevice.value = null
  activeDialog.value = ''
}

function onSaved() {
  closeDialog()
  void reload()
}

async function loadSettings() {
  try {
    const response = await request(`${ENDPOINT}/settings`)
    if (response.ok) settings.value = await response.json()
  } catch {
    // 取不到配置时使用默认值，不阻塞列表
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.装置编号) query.set('keyword', filters.value.装置编号)
  if (filters.value.所属站点) query.set('site', filters.value.所属站点)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('防雷装置列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '防雷接地列表读取失败'
  }
}

onMounted(() => {
  void loadSettings()
  void reload()
})
</script>
