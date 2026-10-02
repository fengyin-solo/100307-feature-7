<template>
  <div v-if="device" class="modal-mask" @click.self="emit('close')">
    <form class="modal-card" @submit.prevent="submit">
      <header class="modal-head">
        <h3>更换浪涌保护模块</h3>
        <button class="link" type="button" @click="emit('close')">关闭</button>
      </header>
      <p class="modal-sub">
        {{ device['装置编号'] }} · {{ device['所属站点'] }}
        ｜当前模块：{{ device['浪涌保护'] || '—' }}
      </p>
      <p class="modal-tip">更换后测试人员与测试日期随本次更换同步更新，台账与复测队列按更换后复测结果重排。</p>
      <div class="form-grid">
        <label class="form-item">
          <span>更换日期 *</span>
          <input v-model="form.date" type="date" required />
        </label>
        <label class="form-item">
          <span>新模块型号 *</span>
          <input v-model="form.module" placeholder="如 DEHN DV M TT 255" required />
        </label>
        <label class="form-item">
          <span>更换/测试人员 *</span>
          <input v-model="form.operator" required />
        </label>
        <label class="form-item">
          <span>更换后接地电阻 (Ω) *</span>
          <input v-model="form.resistance" type="number" step="0.1" min="0" placeholder="更换后当场测试" required />
        </label>
        <label class="form-item form-item-wide">
          <span>更换原因</span>
          <input v-model="form.reason" placeholder="如 SPD 击穿、巡检发现劣化" />
        </label>
      </div>
      <p v-if="form.resistance !== '' && Number(form.resistance) > Number(settings.resistance_limit)" class="warn-text">
        更换后阻值仍超过 {{ settings.resistance_limit }}Ω，装置会继续留在复测队列。
      </p>
      <p v-if="error" class="error-text">{{ error }}</p>
      <footer class="modal-foot">
        <button class="btn" type="button" @click="emit('close')">取消</button>
        <button class="btn primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : '确认更换并复测' }}</button>
      </footer>
    </form>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'

import { request } from '@/api/client'
import type { QueueItem, QueueSettings } from '../queue-ui'

type Device = QueueItem

const props = defineProps<{ device: Device | null; settings: QueueSettings; defaultTester: string }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved'): void }>()

function todayISO() {
  return new Date().toISOString().slice(0, 10)
}

const form = reactive({ date: todayISO(), module: '', operator: '', resistance: '', reason: '' })
const saving = ref(false)
const error = ref('')

watch(
  () => Boolean(props.device),
  (open) => {
    if (open) {
      form.date = todayISO()
      form.module = ''
      form.operator = props.defaultTester
      form.resistance = ''
      form.reason = ''
      error.value = ''
    }
  },
)

async function submit() {
  if (!props.device) return
  saving.value = true
  error.value = ''
  try {
    const response = await request(`/api/lightningprot/${props.device.id}/replace-spd`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...form } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '更换记录未生效，请稍后重试')
    }
    emit('saved')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '浪涌模块更换登记失败'
  } finally {
    saving.value = false
  }
}
</script>
