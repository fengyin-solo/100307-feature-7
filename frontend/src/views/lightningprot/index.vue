<template>
  <section class="page" data-module="lightningprot">
    <header class="page-head">
      <div>
        <h2>防雷接地管理</h2>
        <p class="page-desc">按复测周期排程接地电阻测试：按站点列出下次复测日，电阻超标的单独呈现并标注是哪一次测超的，点开即可登记复测。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出防雷装置台账</button>
      </div>
    </header>

    <div class="tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
        <span v-if="tab.key === 'queue' && queueData" class="tab-badge">{{ queueData.total }}</span>
      </button>
    </div>

    <span v-if="message" class="toast" :class="messageOk ? 'ok' : 'error-text'">{{ message }}</span>

    <!-- ============ 复测队列 ============ -->
    <template v-if="activeTab === 'queue'">
      <div class="stat-row">
        <article class="stat-card stat-fail">
          <span class="stat-label">电阻超标（留队整改）</span>
          <strong class="stat-value">{{ queueData?.counts['电阻超标'] ?? 0 }}</strong>
        </article>
        <article class="stat-card stat-overdue">
          <span class="stat-label">已超期未复测</span>
          <strong class="stat-value">{{ queueData?.counts['已超期'] ?? 0 }}</strong>
        </article>
        <article class="stat-card stat-soon">
          <span class="stat-label">临近复测（{{ queueData?.warn_days ?? 30 }} 天内）</span>
          <strong class="stat-value">{{ queueData?.counts['临近复测'] ?? 0 }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">当前复测周期 / 统计基准日</span>
          <strong class="stat-value small">{{ queueData?.cycle_months ?? 12 }} 个月 · {{ queueData?.as_of ?? '—' }}</strong>
        </article>
      </div>

      <form class="filter-bar" @submit.prevent="loadQueue">
        <label class="filter-item">
          <span>所属站点</span>
          <input v-model="queueSite" placeholder="按站点名称过滤" />
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="queueSite = ''; loadQueue()">显示全部站点</button>
      </form>

      <div v-if="!queueData" class="data-table empty-state" style="padding: 24px">正在加载复测队列…</div>
      <template v-else>
        <section v-for="group in queueData.site_groups" :key="group.所属站点" class="site-group">
          <header class="site-group-head">
            <h3>{{ group.所属站点 }}</h3>
            <span class="site-group-tags">
              <em v-if="group.超标" class="tag tag-fail">超标 {{ group.超标 }}</em>
              <em v-if="group.超期" class="tag tag-overdue">超期 {{ group.超期 }}</em>
              <em v-if="group.临期" class="tag tag-soon">临期 {{ group.临期 }}</em>
              <em class="tag tag-total">在队 {{ group.items.length }}</em>
            </span>
          </header>
          <table class="data-table">
            <thead>
              <tr>
                <th>队列层级</th>
                <th>装置编号</th>
                <th>防雷模块 / 浪涌保护</th>
                <th>上次接地电阻</th>
                <th>上次测试（人员）</th>
                <th>下次复测日</th>
                <th>超期</th>
                <th>超标溯源</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in group.items" :key="String(item.id)" :class="tierRowClass(item.queue_tier)">
                <td><span class="tier-badge" :class="tierClass(item.queue_tier)">{{ item.queue_tier }}</span></td>
                <td>{{ item.装置编号 }}</td>
                <td class="cell-sub">{{ item.防雷模块 }}<br /><span class="muted">{{ item.浪涌保护 }}</span></td>
                <td :class="{ 'res-fail': item.queue_tier === '电阻超标' }">{{ item.接地电阻 }}</td>
                <td>{{ item.上次测试 }}<br /><span class="muted">{{ item.测试人员 }}</span></td>
                <td>{{ item.下次复测日 }}</td>
                <td>
                  <span v-if="item.超期天数 != null" class="overdue-days">超 {{ item.超期天数 }} 天</span>
                  <span v-else class="muted">—</span>
                </td>
                <td>
                  <div v-if="item.超标测试序号" class="fail-trace">
                    第 {{ item.超标测试序号 }}/{{ item.超标测试次数 }} 次测超<br />
                    <span class="muted">{{ item.超标日期 }} · {{ item.超标读数 }} · {{ item.超标测试人员 }}</span>
                  </div>
                  <span v-else class="muted">—</span>
                </td>
                <td class="row-actions">
                  <button class="link" type="button" @click="openRetest(item)">登记复测</button>
                  <button class="link" type="button" @click="openReplace(item)">更换浪涌模块</button>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
        <div v-if="!queueData.site_groups.length" class="data-table empty-state" style="padding: 24px">
          当前没有在队装置：全部装置复测合格且未到下次复测日。
        </div>
      </template>
    </template>

    <!-- ============ 装置台账 ============ -->
    <template v-if="activeTab === 'ledger'">
      <form class="filter-bar" @submit.prevent="loadLedger">
        <label class="filter-item">
          <span>装置编号</span>
          <input v-model="ledgerKeyword" placeholder="按装置编号检索" />
        </label>
        <label class="filter-item">
          <span>所属站点</span>
          <input v-model="ledgerSite" placeholder="按站点检索" />
        </label>
        <label class="filter-item">
          <span>装置状态</span>
          <select v-model="ledgerStatus">
            <option value="">全部</option>
            <option value="合格">合格</option>
            <option value="电阻超标">电阻超标</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetLedgerFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in ledgerColumns" :key="column">{{ column }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in ledgerRows" :key="String(row.id)" :class="{ 'row-fail': row['装置状态'] === '电阻超标' }">
            <td v-for="column in ledgerColumns" :key="column">
              <template v-if="column === '装置状态'">
                <span class="tier-badge" :class="row[column] === '电阻超标' ? 'tier-fail' : 'tier-pass'">{{ row[column] }}</span>
              </template>
              <template v-else-if="column === '下次复测日'">
                {{ row[column] }}
                <div v-if="row['超期天数'] != null" class="overdue-days">已超 {{ row['超期天数'] }} 天</div>
              </template>
              <template v-else>{{ row[column] ?? '—' }}</template>
            </td>
            <td class="row-actions">
              <button class="link" type="button" @click="openRetest(row)">登记复测</button>
              <button class="link" type="button" @click="openReplace(row)">更换浪涌模块</button>
              <button class="link" type="button" @click="openHistory(row)">测试记录</button>
            </td>
          </tr>
          <tr v-if="!ledgerRows.length">
            <td :colspan="ledgerColumns.length + 1" class="empty-state">暂无防雷装置数据</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot">
        <span>共 {{ ledgerTotal }} 台防雷装置 · 台账状态与复测队列同源，不存在两个结论</span>
      </footer>
    </template>

    <!-- ============ 周期设置 ============ -->
    <template v-if="activeTab === 'settings'">
      <div class="settings-panel">
        <h3>复测周期</h3>
        <p class="page-desc">
          接地电阻按固定周期复测。调整周期并保存后，所有在账装置的下次复测日都会按新周期、
          从各自最近一次测试日期重新排一遍；新登记装置默认沿用该周期。
        </p>
        <form class="settings-form" @submit.prevent="saveCycle">
          <label class="filter-item">
            <span>复测周期（月）</span>
            <input v-model.number="cycleInput" type="number" min="1" max="60" style="width: 120px" />
          </label>
          <button class="btn primary" type="submit">保存并重排队列</button>
        </form>
        <ul class="settings-notes">
          <li>临期提醒窗口：{{ retestSettings?.warn_days ?? 30 }} 天（到期前进入「临近复测」）</li>
          <li>接地电阻合格线：≤ {{ retestSettings?.resistance_limit ?? 10 }}Ω，读数大于该值判为电阻超标</li>
          <li>在账装置数：{{ retestSettings?.rescheduled_devices ?? 0 }} 台（保存时逐台重排）</li>
        </ul>
      </div>
    </template>

    <!-- ============ 复测/更换 弹窗 ============ -->
    <div v-if="dialog" class="modal-mask" @click.self="dialog = null">
      <form class="modal" @submit.prevent="submitDialog">
        <h3>{{ dialog.mode === 'replace' ? '登记浪涌保护模块更换' : '登记接地电阻复测' }}</h3>
        <p class="page-desc">
          {{ dialog.item.装置编号 }} · {{ dialog.item.所属站点 }}
          <template v-if="dialog.item.下次复测日"> · 当前下次复测日 {{ dialog.item.下次复测日 }}</template>
        </p>
        <label v-if="dialog.mode === 'replace'" class="form-field">
          <span>更换后浪涌保护模块型号 *</span>
          <input v-model="dialog.form.浪涌保护" placeholder="例如 OBO V25-B+C/3+NPE" />
        </label>
        <div v-if="dialog.mode === 'replace'" class="form-row">
          <label class="form-field">
            <span>防雷模块（如有变更）</span>
            <input v-model="dialog.form.防雷模块" :placeholder="String(dialog.item.防雷模块 || '模块型号')" />
          </label>
        </div>
        <div class="form-row">
          <label class="form-field">
            <span>本次接地电阻 (Ω) *</span>
            <input v-model="dialog.form.接地电阻" type="number" step="0.1" min="0" placeholder="如 4.2，大于 10Ω 判超标" />
          </label>
          <label class="form-field">
            <span>测试日期 *</span>
            <input v-model="dialog.form.测试日期" type="date" />
          </label>
          <label class="form-field">
            <span>测试人员 *</span>
            <input v-model="dialog.form.测试人员" placeholder="现场测试人" />
          </label>
        </div>
        <p class="form-hint">
          合格（≤10Ω）：下次复测日按测试日期+{{ queueData?.cycle_months ?? retestSettings?.cycle_months ?? 12 }}个月重排，装置退出复测队列；
          仍超标：留队继续整改，本次记录即「哪一次测超的」溯源依据。
        </p>
        <footer class="modal-foot">
          <span v-if="dialogError" class="error-text">{{ dialogError }}</span>
          <div>
            <button class="btn ghost" type="button" @click="dialog = null">取消</button>
            <button class="btn primary" type="submit">提交</button>
          </div>
        </footer>
      </form>
    </div>

    <!-- ============ 测试记录弹窗 ============ -->
    <div v-if="historyEntry" class="modal-mask" @click.self="historyEntry = null">
      <div class="modal">
        <h3>测试记录 · {{ historyEntry.装置编号 }}</h3>
        <p class="page-desc">{{ historyEntry.所属站点 }} · 台账状态：{{ historyEntry.装置状态 }}</p>
        <table class="data-table">
          <thead>
            <tr>
              <th>序</th><th>日期</th><th>接地电阻</th><th>测试人员</th><th>来源</th><th>判定</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(t, idx) in historyEntry.tests" :key="idx" :class="{ 'row-fail': !t.passed }">
              <td>{{ idx + 1 }}</td>
              <td>{{ t.date }}</td>
              <td>{{ t.resistance_text }}</td>
              <td>{{ t.tester }}</td>
              <td>{{ t.source }}</td>
              <td>
                <span class="tier-badge" :class="t.passed ? 'tier-pass' : 'tier-fail'">
                  {{ t.passed ? '合格' : '超标' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <footer class="modal-foot">
          <span></span>
          <div><button class="btn primary" type="button" @click="historyEntry = null">关闭</button></div>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type QueueItem = {
  id: number
  装置编号: string
  所属站点: string
  防雷模块: string
  浪涌保护: string
  接地电阻: string
  上次测试: string
  测试人员: string
  下次复测日: string
  装置状态: string
  queue_tier: '电阻超标' | '已超期' | '临近复测'
  超期天数: number | null
  超标测试序号: number | null
  超标测试次数: number | null
  超标日期: string | null
  超标读数: string | null
  超标测试人员: string | null
}

type SiteGroup = {
  所属站点: string
  items: QueueItem[]
  超标: number
  超期: number
  临期: number
}

type QueueData = {
  as_of: string
  cycle_months: number
  warn_days: number
  resistance_limit: number
  total: number
  counts: Record<string, number>
  site_groups: SiteGroup[]
}

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/lightningprot'
const tabs = [
  { key: 'queue', label: '复测队列' },
  { key: 'ledger', label: '装置台账' },
  { key: 'settings', label: '周期设置' },
] as const
type TabKey = (typeof tabs)[number]['key']

const activeTab = ref<TabKey>('queue')
const message = ref('')
const messageOk = ref(true)

// ---- 复测队列 ----
const queueData = ref<QueueData | null>(null)
const queueSite = ref('')

// ---- 装置台账 ----
const ledgerRows = ref<Row[]>([])
const ledgerTotal = ref(0)
const ledgerKeyword = ref('')
const ledgerSite = ref('')
const ledgerStatus = ref('')
const ledgerColumns = ['装置编号', '所属站点', '接地电阻', '防雷模块', '浪涌保护', '上次测试', '测试人员', '下次复测日', '装置状态']

// ---- 周期设置 ----
const retestSettings = ref<{ cycle_months: number; warn_days: number; resistance_limit: number; rescheduled_devices: number } | null>(null)
const cycleInput = ref<number>(12)

// ---- 弹窗 ----
type DialogMode = 'retest' | 'replace'
const dialog = ref<{ mode: DialogMode; item: QueueItem | Row; form: Record<string, string> } | null>(null)
const dialogError = ref('')
const historyEntry = ref<(Row & { tests: Array<Record<string, string | number | boolean>> }) | null>(null)

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

function flash(text: string, ok = true) {
  message.value = text
  messageOk.value = ok
  window.setTimeout(() => {
    if (message.value === text) message.value = ''
  }, 6000)
}

async function loadQueue() {
  const query = new URLSearchParams()
  if (queueSite.value) query.set('site', queueSite.value)
  const response = await request(`${ENDPOINT}/retest-queue?${query.toString()}`)
  if (!response.ok) throw new Error('复测队列读取失败')
  queueData.value = (await response.json()) as QueueData
}

async function loadSettings() {
  const response = await request(`${ENDPOINT}/retest-settings`)
  if (!response.ok) throw new Error('复测周期设置读取失败')
  const settings = (await response.json()) as { cycle_months: number; warn_days: number; resistance_limit: number; rescheduled_devices: number }
  retestSettings.value = settings
  cycleInput.value = settings.cycle_months
}

async function loadLedger() {
  const query = new URLSearchParams()
  if (ledgerKeyword.value) query.set('keyword', ledgerKeyword.value)
  if (ledgerSite.value) query.set('site', ledgerSite.value)
  if (ledgerStatus.value) query.set('status', ledgerStatus.value)
  query.set('size', '200')
  const response = await request(`${ENDPOINT}?${query.toString()}`)
  if (!response.ok) throw new Error('装置台账读取失败')
  const payload = await response.json()
  ledgerRows.value = payload.items ?? []
  ledgerTotal.value = payload.total ?? ledgerRows.value.length
}

function resetLedgerFilters() {
  ledgerKeyword.value = ''
  ledgerSite.value = ''
  ledgerStatus.value = ''
  void loadLedger()
}

function switchTab(key: TabKey) {
  activeTab.value = key
  if (key === 'ledger' && !ledgerRows.value.length) void loadLedger()
  if (key === 'settings') void loadSettings()
  if (key === 'queue') void loadQueue()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

// ---- 复测 / 更换 ----
function makeDialog(mode: DialogMode, item: QueueItem | Row) {
  return {
    mode,
    item,
    form: {
      接地电阻: '',
      测试日期: todayISO(),
      测试人员: '',
      浪涌保护: (item.浪涌保护 as string) ?? '',
      防雷模块: (item.防雷模块 as string) ?? '',
    },
  }
}

function openRetest(item: QueueItem | Row) {
  dialogError.value = ''
  dialog.value = makeDialog('retest', item)
}

function openReplace(item: QueueItem | Row) {
  dialogError.value = ''
  dialog.value = makeDialog('replace', item)
}

async function submitDialog() {
  if (!dialog.value) return
  const mode = dialog.value.mode
  const id = dialog.value.item.id
  const path = mode === 'replace' ? `${ENDPOINT}/${id}/spd-replacement` : `${ENDPOINT}/${id}/retest`
  dialogError.value = ''
  try {
    const response = await request(path, {
      method: 'POST',
      body: JSON.stringify({ values: dialog.value.form }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      dialogError.value = payload.message || '提交未生效，请稍后重试'
      return
    }
    dialog.value = null
    flash(payload.message, true)
    await Promise.all([loadQueue(), loadLedger(), loadSettings()])
  } catch (error) {
    dialogError.value = error instanceof Error ? error.message : '提交失败'
  }
}

// ---- 周期设置 ----
async function saveCycle() {
  try {
    const response = await request(`${ENDPOINT}/retest-settings`, {
      method: 'PUT',
      body: JSON.stringify({ values: { cycle_months: cycleInput.value } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      flash(payload.message || '周期调整未生效', false)
      return
    }
    flash(payload.message, true)
    await Promise.all([loadSettings(), loadQueue()])
  } catch (error) {
    flash(error instanceof Error ? error.message : '周期调整失败', false)
  }
}

// ---- 测试记录 ----
async function openHistory(row: Row) {
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) throw new Error('测试记录读取失败')
    historyEntry.value = await response.json()
  } catch (error) {
    flash(error instanceof Error ? error.message : '测试记录读取失败', false)
  }
}

// ---- 展示样式辅助 ----
function tierClass(tier: string) {
  if (tier === '电阻超标') return 'tier-fail'
  if (tier === '已超期') return 'tier-overdue'
  return 'tier-soon'
}
function tierRowClass(tier: string) {
  if (tier === '电阻超标') return 'row-fail'
  if (tier === '已超期') return 'row-overdue'
  return ''
}

onMounted(() => {
  void loadQueue().catch((error) => flash(error.message, false))
  void loadSettings().catch(() => undefined)
})
</script>

<style scoped>
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 12px; }
.tab { border: none; background: none; padding: 8px 16px; cursor: pointer; font-size: 14px; color: var(--muted); border-bottom: 2px solid transparent; }
.tab.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
.tab-badge { background: #fee4e2; color: #b42318; border-radius: 10px; padding: 0 7px; font-size: 11px; font-style: normal; margin-left: 4px; }

.toast { display: block; margin-bottom: 10px; font-size: 13px; padding: 8px 12px; border-radius: 6px; }
.toast.ok { background: #e8f7ee; color: #175c32; }

.stat-fail .stat-value { color: #b42318; }
.stat-overdue .stat-value { color: #b54708; }
.stat-soon .stat-value { color: #b54708; }
.stat-value.small { font-size: 15px; }

.site-group { margin-bottom: 18px; }
.site-group-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.site-group-head h3 { margin: 0; font-size: 15px; }
.site-group-tags { display: flex; gap: 6px; }
.tag { font-style: normal; font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.tag-fail { background: #fee4e2; color: #b42318; }
.tag-overdue { background: #fef3c7; color: #92400e; }
.tag-soon { background: #ffedd5; color: #9a3412; }
.tag-total { background: #eef2ff; color: #3730a3; }

.tier-badge { font-style: normal; font-size: 12px; padding: 2px 8px; border-radius: 10px; white-space: nowrap; }
.tier-fail { background: #fee4e2; color: #b42318; }
.tier-overdue { background: #fef3c7; color: #92400e; }
.tier-soon { background: #ffedd5; color: #9a3412; }
.tier-pass { background: #e8f7ee; color: #175c32; }

.row-fail { background: #fff6f5; }
.row-overdue { background: #fffdf0; }
.res-fail { color: #b42318; font-weight: 600; }
.overdue-days { color: #b54708; font-size: 12px; }
.cell-sub { line-height: 1.4; }
.muted { color: var(--muted); font-size: 12px; }
.fail-trace { line-height: 1.5; color: #b42318; font-size: 12px; }

.settings-panel { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 16px 20px; max-width: 720px; }
.settings-form { display: flex; gap: 12px; align-items: flex-end; margin: 14px 0; }
.settings-notes { color: var(--muted); font-size: 13px; line-height: 2; padding-left: 18px; }

.modal-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal { background: #fff; border-radius: 10px; padding: 20px 24px; width: 640px; max-width: calc(100vw - 40px); max-height: 86vh; overflow: auto; }
.modal h3 { margin: 0 0 4px; font-size: 16px; }
.form-row { display: flex; gap: 12px; }
.form-field { display: flex; flex-direction: column; gap: 4px; flex: 1; margin: 10px 0; font-size: 13px; }
.form-field input, .form-field select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }
.form-hint { color: var(--muted); font-size: 12px; line-height: 1.6; background: #f8fafc; padding: 8px 10px; border-radius: 6px; }
.modal-foot { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; }
.modal-foot > div { display: flex; gap: 8px; }
.filter-item select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
</style>
