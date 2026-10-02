<template>
  <div v-if="device" class="modal-mask" @click.self="emit('close')">    <section class="modal-card detail-card">
      <header class="modal-head">
        <h3>装置档案与测试历史</h3>
        <button class="link" type="button" @click="emit('close')">关闭</button>
      </header>

      <dl class="detail-grid">
        <div><dt>装置编号</dt><dd>{{ device['装置编号'] }}</dd></div>
        <div><dt>所属站点</dt><dd>{{ device['所属站点'] }}</dd></div>
        <div><dt>防雷模块</dt><dd>{{ device['防雷模块'] || '—' }}</dd></div>
        <div><dt>浪涌保护</dt><dd>{{ device['浪涌保护'] || '—' }}</dd></div>
        <div><dt>当前装置状态</dt><dd>
          <span :class="['tag', stateClass(device['装置状态'])]">{{ device['装置状态'] }}</span>
        </dd></div>
        <div><dt>复测队列</dt><dd>
          <span v-if="device.in_queue" :class="['tag', queueClass(device['队列状态'])]">{{ device['队列状态'] }}</span>
          <span v-else class="tag tag-ok">已退出（合格）</span>
        </dd></div>
        <div><dt>最近测试</dt><dd>{{ device['上次测试'] || '—' }} · {{ device['测试人员'] || '—' }}</dd></div>
        <div><dt>最近阻值</dt><dd>{{ device.接地电阻 === null ? '—' : `${device.接地电阻}Ω` }}</dd></div>
        <div><dt>下次复测日</dt><dd>{{ device['下次复测日'] || '—' }}</dd></div>
      </dl>

      <p v-if="device['超标说明']" class="warn-text">{{ device['超标说明'] }}</p>

      <h4 class="detail-h">测试记录</h4>
      <table class="data-table history-table">
        <thead>
          <tr><th>测试日期</th><th>接地电阻</th><th>结论</th><th>测试人员</th><th>备注</th></tr>
        </thead>
        <tbody>
          <tr v-for="(test, idx) in testsReversed" :key="idx">
            <td>{{ test.date }}</td>
            <td>{{ test.resistance }}Ω</td>
            <td><span :class="['tag', test.result === '合格' ? 'tag-ok' : 'tag-bad']">{{ test.result }}</span></td>
            <td>{{ test.tester }}</td>
            <td>{{ test.remark || '—' }}</td>
          </tr>
          <tr v-if="!testsReversed.length">
            <td colspan="5" class="empty-state">暂无测试记录</td>
          </tr>
        </tbody>
      </table>

      <h4 class="detail-h">浪涌保护模块更换记录</h4>
      <table class="data-table history-table">
        <thead>
          <tr><th>更换日期</th><th>模块型号</th><th>人员</th><th>更换后阻值</th><th>结论</th><th>原因</th></tr>
        </thead>
        <tbody>
          <tr v-for="(item, idx) in replacementsReversed" :key="idx">
            <td>{{ item.date }}</td>
            <td>{{ item.module }}</td>
            <td>{{ item.operator }}</td>
            <td>{{ item.post_resistance }}Ω</td>
            <td><span :class="['tag', item.post_result === '合格' ? 'tag-ok' : 'tag-bad']">{{ item.post_result }}</span></td>
            <td>{{ item.reason || '—' }}</td>
          </tr>
          <tr v-if="!replacementsReversed.length">
            <td colspan="6" class="empty-state">暂无更换记录</td>
          </tr>
        </tbody>
      </table>

      <footer class="modal-foot">
        <button class="btn" type="button" @click="emit('close')">关闭</button>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { stateClass, queueClass, type QueueItem } from '../queue-ui'

type TestRecord = { date: string; resistance: number; result: string; tester: string; remark: string }
type ReplacementRecord = {
  date: string
  module: string
  operator: string
  post_resistance: number
  post_result: string
  reason: string
}

const props = defineProps<{ device: QueueItem | null }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const testsReversed = computed<TestRecord[]>(() =>
  ((props.device?.测试记录 ?? []) as unknown as TestRecord[]).slice().reverse(),
)
const replacementsReversed = computed<ReplacementRecord[]>(() =>
  ((props.device?.更换记录 ?? []) as unknown as ReplacementRecord[]).slice().reverse(),
)
</script>
