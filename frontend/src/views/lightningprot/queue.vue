<template>
  <section class="page" data-module="lightningprot-queue">
    <header class="page-head">
      <div>
        <h2>防雷装置复测队列</h2>
        <p class="page-desc">
          按站点列出下次复测日：电阻超标的单独呈现并标注测超记录，超期、即将到期的排在前面；
          点开任一装置可直接登记复测，合格后自动退出队列。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/lightningprot">返回装置台账</RouterLink>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card stat-danger">
        <span class="stat-label">电阻超标（待复测）</span>
        <strong class="stat-value">{{ overview.counts?.['电阻超标'] ?? 0 }}</strong>
      </article>
      <article class="stat-card stat-danger">
        <span class="stat-label">已超期</span>
        <strong class="stat-value">{{ overdueCount }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">{{ overview.settings?.warn_days ?? 30 }} 天内到期</span>
        <strong class="stat-value">{{ overview.counts?.['即将到期'] ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">队列总数 / 合格退出</span>
        <strong class="stat-value">{{ overview.queued_total ?? 0 }} / {{ overview.rested?.length ?? 0 }}</strong>
      </article>
    </div>

    <form class="setting-bar" @submit.prevent="saveSettings">
      <span class="setting-title">复测口径</span>
      <label class="filter-item">
        <span>复测周期（月）</span>
        <input v-model.number="settingsForm.cycle_months" type="number" min="1" max="60" />
      </label>
      <label class="filter-item">
        <span>到期预警（天）</span>
        <input v-model.number="settingsForm.warn_days" type="number" min="0" max="365" />
      </label>
      <label class="filter-item">
        <span>电阻限值（Ω）</span>
        <input v-model.number="settingsForm.resistance_limit" type="number" step="0.1" min="0" />
      </label>
      <button class="btn primary" type="submit" :disabled="savingSettings">
        {{ savingSettings ? '保存中…' : '调整并重排' }}
      </button>
      <span class="setting-hint">保存后全部装置的下次复测日按新口径重排</span>
    </form>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>站点</span>
        <select v-model="siteFilter">
          <option value="">全部站点</option>
          <option v-for="site in overview.sites ?? []" :key="site" :value="site">{{ site }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>队列状态</span>
        <select v-model="stateFilter">
          <option value="">全部</option>
          <option v-for="state in queueStateOptions" :key="state" :value="state">{{ state }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <span class="today-hint">今天 {{ overview.today }}</span>
    </form>

    <p v-if="settingsMessage" :class="settingsOk ? 'ok-text' : 'error-text'">{{ settingsMessage }}</p>

    <!-- 电阻超标专区：标注是哪一次测超的 -->
    <section class="queue-section">
      <h3 class="section-title">
        <span class="title-dot dot-bad"></span>电阻超标装置
        <em class="section-count">{{ overview.counts?.['电阻超标'] ?? 0 }} 台</em>
      </h3>
      <table v-if="failedItems.length" class="data-table fail-table">
        <thead>
          <tr>
            <th>站点 / 装置</th>
            <th>最近阻值</th>
            <th>下次复测日</th>
            <th>测超记录</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in failedItems" :key="String(item.id)" class="row-bad">
            <td>
              <strong>{{ item.所属站点 }}</strong>
              <span class="sub-text">{{ item.装置编号 }} · {{ item.浪涌保护 }}</span>
            </td>
            <td><strong class="bad-text">{{ item.接地电阻 }}Ω</strong></td>
            <td>{{ item.下次复测日 }}<span class="sub-text">{{ daysLabel(item.距复测天数) }}</span></td>
            <td class="failure-cell">{{ item.超标说明 }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="openRetest(item)">登记复测</button>
              <button class="link" type="button" @click="openHistory(item)">档案</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-block">当前没有电阻超标的装置。</p>
    </section>

    <!-- 按站点分组的复测队列 -->
    <section class="queue-section">
      <h3 class="section-title">
        <span class="title-dot dot-main"></span>复测队列（按站点，超期/临期在前）
        <em class="section-count">{{ overview.queued_total ?? 0 }} 台</em>
      </h3>
      <template v-if="queueGroups.length">
        <div v-for="group in queueGroups" :key="group.site" class="site-group">
          <h4 class="site-group-title">{{ group.site }}<em>{{ group.items.length }} 台</em></h4>
          <table class="data-table">
            <thead>
              <tr>
                <th>排序</th>
                <th>装置编号</th>
                <th>队列状态</th>
                <th>下次复测日</th>
                <th>最近测试</th>
                <th>接地电阻</th>
                <th>浪涌保护</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, idx) in group.items" :key="String(item.id)">
                <td>{{ idx + 1 }}</td>
                <td>{{ item.装置编号 }}</td>
                <td><span :class="['tag', queueClass(item.队列状态)]">{{ item.队列状态 }}</span></td>
                <td>
                  {{ item.下次复测日 }}
                  <span :class="['sub-text', item.距复测天数 !== null && item.距复测天数 < 0 ? 'bad-text' : '']">
                    {{ daysLabel(item.距复测天数) }}
                  </span>
                </td>
                <td>{{ item.上次测试 }}<span class="sub-text">{{ item.测试人员 }}</span></td>
                <td>{{ item.接地电阻 === null ? '—' : `${item.接地电阻}Ω` }}</td>
                <td>{{ item.浪涌保护 }}</td>
                <td class="row-actions">
                  <button class="link" type="button" @click="openRetest(item)">登记复测</button>
                  <button class="link" type="button" @click="openSpd(item)">换SPD</button>
                  <button class="link" type="button" @click="openHistory(item)">档案</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
      <p v-else class="empty-block">所选条件下没有在队装置。</p>
    </section>

    <!-- 已退出队列（复测合格） -->
    <section class="queue-section">
      <h3 class="section-title collapsed-title" @click="showRested = !showRested">
        <span class="title-dot dot-ok"></span>已退出队列（复测合格，未到复测日）
        <em class="section-count">{{ restedItems.length }} 台</em>
        <span class="collapse-hint">{{ showRested ? '收起 ▲' : '展开 ▼' }}</span>
      </h3>
      <table v-if="showRested && restedItems.length" class="data-table">
        <thead>
          <tr>
            <th>站点</th>
            <th>装置编号</th>
            <th>装置状态</th>
            <th>下次复测日</th>
            <th>最近测试</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in restedItems" :key="String(item.id)">
            <td>{{ item.所属站点 }}</td>
            <td>{{ item.装置编号 }}</td>
            <td><span class="tag tag-ok">{{ item.装置状态 }}</span></td>
            <td>{{ item.下次复测日 }}<span class="sub-text">{{ daysLabel(item.距复测天数) }}</span></td>
            <td>{{ item.上次测试 }}<span class="sub-text">{{ item.测试人员 }}</span></td>
            <td class="row-actions">
              <button class="link" type="button" @click="openRetest(item)">补测登记</button>
              <button class="link" type="button" @click="openHistory(item)">档案</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <RetestDialog
      :device="activeDialog === 'retest' ? activeDevice : null"
      :settings="currentSettings"
      :default-tester="store.operator"
      @close="activeDevice = null; activeDialog = ''"
      @saved="onSaved"
    />
    <SpdDialog
      :device="activeDialog === 'spd' ? activeDevice : null"
      :settings="currentSettings"
      :default-tester="store.operator"
      @close="activeDevice = null; activeDialog = ''"
      @saved="onSaved"
    />
    <HistoryDrawer :device="historyDevice" @close="historyDevice = null" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import RetestDialog from './components/RetestDialog.vue'
import SpdDialog from './components/SpdDialog.vue'
import HistoryDrawer from './components/HistoryDrawer.vue'
import { daysLabel, queueClass, type QueueItem, type QueueSettings } from './queue-ui'

type QueueGroup = { site: string; items: QueueItem[] }
type Overview = {
  today: string
  settings: QueueSettings
  sites: string[]
  counts: Record<string, number>
  queued_total: number
  groups: QueueGroup[]
  rested: QueueItem[]
}

const store = useSessionStore()
const queueStateOptions = ['电阻超标', '已超期', '模块劣化·已超期', '即将到期', '模块劣化', '已安排']

const overview = ref<Partial<Overview>>({})
const siteFilter = ref('')
const stateFilter = ref('')
const showRested = ref(false)
const errorMessage = ref('')

const activeDevice = ref<QueueItem | null>(null)
const activeDialog = ref<'retest' | 'spd' | ''>('')
const historyDevice = ref<QueueItem | null>(null)

const savingSettings = ref(false)
const settingsMessage = ref('')
const settingsOk = ref(true)
const settingsForm = reactive<QueueSettings>({ cycle_months: 12, warn_days: 30, resistance_limit: 10 })

const currentSettings = computed<QueueSettings>(
  () => overview.value.settings ?? { cycle_months: 12, warn_days: 30, resistance_limit: 10 },
)

// 已超期统计含“模块劣化·已超期”。
const overdueCount = computed(
  () =>
    (overview.value.counts?.['已超期'] ?? 0) + (overview.value.counts?.['模块劣化·已超期'] ?? 0),
)

function inFilter(item: QueueItem): boolean {
  return (!stateFilter.value || item.队列状态 === stateFilter.value)
}

const queueGroups = computed<QueueGroup[]>(() =>
  (overview.value.groups ?? [])
    .map((group) => ({ site: group.site, items: group.items.filter(inFilter) }))
    .filter((group) => group.items.length > 0),
)

const failedItems = computed<QueueItem[]>(() => {
  const items = (overview.value.groups ?? []).flatMap((group) => group.items)
  return items.filter((item) => item.队列状态 === '电阻超标' && inFilter(item))
})

const restedItems = computed<QueueItem[]>(() =>
  (overview.value.rested ?? []).filter(
    (item) => !siteFilter.value || item.所属站点 === siteFilter.value,
  ),
)

function resetFilters() {
  siteFilter.value = ''
  stateFilter.value = ''
  void reload()
}

function openRetest(item: QueueItem) {
  activeDevice.value = item
  activeDialog.value = 'retest'
}

function openSpd(item: QueueItem) {
  activeDevice.value = item
  activeDialog.value = 'spd'
}

function openHistory(item: QueueItem) {
  historyDevice.value = item
}

function onSaved() {
  activeDevice.value = null
  activeDialog.value = ''
  settingsMessage.value = ''
  void reload()
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (siteFilter.value) query.set('site', siteFilter.value)
  if (stateFilter.value) query.set('state', stateFilter.value)
  try {
    const response = await request(`/api/lightningprot/retest-queue?${query.toString()}`)
    if (!response.ok) throw new Error('复测队列读取失败')
    const payload = (await response.json()) as Overview
    overview.value = payload
    Object.assign(settingsForm, payload.settings)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复测队列读取失败'
  }
}

async function saveSettings() {
  savingSettings.value = true
  settingsMessage.value = ''
  try {
    const response = await request('/api/lightningprot/settings', {
      method: 'PUT',
      body: JSON.stringify({ values: { ...settingsForm } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '复测周期保存失败')
    settingsOk.value = true
    settingsMessage.value = payload.message
    await reload()
  } catch (error) {
    settingsOk.value = false
    settingsMessage.value = error instanceof Error ? error.message : '复测周期保存失败'
  } finally {
    savingSettings.value = false
  }
}

onMounted(reload)
</script>
