<template>
  <div v-if="device" class="modal-mask" @click.self="emit('close')">
    <form class="modal-card" @submit.prevent="submit">
      <header class="modal-head">
        <h3>登记复测结果</h3>
        <button class="link" type="button" @click="emit('close')">关闭</button>
      </header>
      <p class="modal-sub">
        {{ device['装置编号'] }} · {{ device['所属站点'] }}
        ｜限值 {{ settings.resistance_limit }}Ω ｜下次复测日 {{ device['下次复测日'] || '—' }}
      </p>
      <div class="form-grid">
        <label class="form-item">
          <span>测试日期 *</span>
          <input v-model="form.date" type="date" required />
        </label>
        <label class="form-item">
          <span>接地电阻 (Ω) *</span>
          <input v-model="form.resistance" type="number" step="0.1" min="0" placeholder="如 4.2" required />
        </label>
        <label class="form-item">
          <span>测试人员 *</span>
          <input v-model="form.tester" placeholder="谁测的登记谁" required />
        </label>
        <label class="form-item form-item-wide">
          <span>备注</span>
          <input v-model="form.remark" placeholder="整改情况、天气、仪表编号等" />
        </label>
      </div>
      <p v-if="form.resistance !== '' && Number(form.resistance) > Number(settings.resistance_limit)" class="warn-text">
        阻值超过 {{ settings.resistance_limit }}Ω，提交后判定为电阻超标，装置继续留在复测队列。
      </p>
      <p v-if="error" class="error-text">{{ error }}</p>
      <footer class="modal-foot">
        <button class="btn" type="button" @click="emit('close')">取消</button>
        <button class="btn primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : '提交复测结果' }}</button>
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

const form = reactive({ date: todayISO(), resistance: '', tester: '', remark: '' })
const saving = ref(false)
const error = ref('')

watch(
  () => Boolean(props.device),
  (open) => {
    if (open) {
      form.date = todayISO()
      form.resistance = ''
      form.tester = props.defaultTester
      form.remark = ''
      error.value = ''
    }
  },
)

async function submit() {
  if (!props.device) return
  saving.value = true
  error.value = ''
  try {
    const response = await request(`/api/lightningprot/${props.device.id}/tests`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...form } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '复测结果未生效，请稍后重试')
    }
    emit('saved')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '复测登记失败'
  } finally {
    saving.value = false
  }
}
</script>
