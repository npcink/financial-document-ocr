<template>
  <div class="progress-tracker">
    <div class="progress-header">
      <h4 class="progress-title">处理进度</h4>
      <el-tag :type="statusTagType" size="small" effect="dark">
        {{ statusLabel }}
      </el-tag>
    </div>

    <div class="progress-bar-wrap">
      <div class="progress-bar">
        <div
          class="progress-bar__fill"
          :class="{ 'progress-bar__fill--indeterminate': !total }"
          :style="{ width: percentage + '%' }"
        />
      </div>
      <span class="progress-percent">{{ percentage }}%</span>
    </div>

    <div class="progress-stats" v-if="total > 0">
      <span>{{ processed }} / {{ total }} 个文件已处理</span>
      <span v-if="estimateText" class="progress-estimate">{{ estimateText }}</span>
    </div>

    <div class="progress-step" v-if="status === 'queued' || status === 'processing'">
      <span class="step-icon">{{ currentStepIcon }}</span>
      <span class="step-text">{{ currentStepText }}</span>
    </div>

    <div class="progress-error" v-if="errorMessage">
      <el-alert :title="errorMessage" type="error" :closable="false" show-icon />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  total: { type: Number, default: 0 },
  processed: { type: Number, default: 0 },
  status: { type: String, default: 'pending' },
  errorMessage: { type: String, default: '' },
  etaSeconds: { type: Number, default: null },
  queueEtaSeconds: { type: Number, default: null },
  queueAheadCount: { type: Number, default: 0 },
})

const percentage = computed(() => {
  if (!props.total) return 0
  return Math.min(100, Math.round((props.processed / props.total) * 100))
})

const statusLabel = computed(() => {
  const map = {
    uploaded: '已上传',
    queued: '排队中',
    pending: '等待处理',
    processing: '处理中',
    completed: '已完成',
    partial_failed: '部分失败',
    timeout_partial: '超时部分完成',
    failed: '失败',
  }
  return map[props.status] || props.status
})

const statusTagType = computed(() => {
  const map = {
    uploaded: 'info',
    queued: 'warning',
    pending: 'warning',
    processing: 'primary',
    completed: 'success',
    partial_failed: 'warning',
    timeout_partial: 'warning',
    failed: 'danger',
  }
  return map[props.status] || 'info'
})

const currentStepText = computed(() => {
  if (props.status === 'queued') {
    if (props.queueAheadCount > 0) return `等待前面 ${props.queueAheadCount} 个任务完成...`
    return '等待 worker 空闲...'
  }
  const pct = percentage.value
  if (pct < 20) return '🔍 正在识别图片文字...'
  if (pct < 50) return '🧠 AI 正在分析票据类型...'
  if (pct < 80) return '📝 正在提取关键字段...'
  return '✅ 正在整理表格数据...'
})

const currentStepIcon = computed(() => {
  return ''
})

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return ''
  const totalSeconds = Math.max(0, Math.round(Number(seconds)))
  if (totalSeconds < 60) return totalSeconds <= 10 ? '不到 10 秒' : `约 ${totalSeconds} 秒`
  const minutes = Math.round(totalSeconds / 60)
  if (minutes < 60) return `约 ${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  const restMinutes = minutes % 60
  return restMinutes ? `约 ${hours} 小时 ${restMinutes} 分钟` : `约 ${hours} 小时`
}

const estimateText = computed(() => {
  if (props.status === 'queued') {
    const eta = formatDuration(props.queueEtaSeconds)
    if (eta && props.queueAheadCount > 0) return `预计 ${eta} 后开始`
    if (eta) return `当前排在最前，预计 ${eta} 后开始`
    if (props.queueAheadCount === 0) return '当前排在最前'
    return ''
  }
  if (props.status === 'processing') {
    const eta = formatDuration(props.etaSeconds)
    return eta ? `预计剩余 ${eta}` : ''
  }
  return ''
})
</script>

<style scoped>
.progress-tracker {
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px 24px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.progress-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.progress-bar-wrap {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 10px;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: var(--color-border);
  border-radius: 99px;
  overflow: hidden;
}

.progress-bar__fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), var(--color-primary-light));
  border-radius: 99px;
  transition: width 0.5s ease;
}

.progress-bar__fill--indeterminate {
  width: 40% !important;
  animation: progress-indeterminate 1.4s ease-in-out infinite;
}

@keyframes progress-indeterminate {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}

.progress-percent {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-primary);
  min-width: 40px;
  text-align: right;
}

.progress-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.progress-estimate {
  color: var(--color-text);
}

.progress-step {
  margin-top: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.step-icon {
  font-size: 16px;
}

.progress-error {
  margin-top: 14px;
}
</style>
