<template>
  <div class="result-table">
    <el-alert
      v-if="failedCount"
      :title="`${failedCount} 条记录识别失败。请切换至 JSON 视图查看详细错误，或点击表格中的「重试」按钮重新处理`"
      type="error"
      :closable="false"
      show-icon
      class="failure-alert"
    />

    <div class="table-toolbar" v-if="showToolbar">
      <div class="toolbar-info">
        <span>{{ resultCountText }}</span>
        <el-tag v-if="failedCount" type="danger" size="small" effect="plain">
          {{ failedCount }} 条失败
        </el-tag>
        <el-tag v-if="lowConfidenceCount" type="warning" size="small" effect="plain">
          {{ lowConfidenceCount }} 个低置信度字段
        </el-tag>
      </div>
      <div class="toolbar-actions">
        <el-button
          v-if="hasMoreResults"
          size="default"
          @click="$emit('load-more')"
          :loading="loadingMoreResults"
        >
          加载更多
        </el-button>
        <el-button
          v-if="failedCount"
          type="warning"
          plain
          size="default"
          @click="$emit('retry-all')"
          :loading="retryAllLoading"
        >
          重试全部 ({{ failedCount }})
        </el-button>
        <el-button
          :icon="DownloadIcon"
          size="default"
          @click="$emit('export-csv')"
          :loading="exportLoading"
        >
          导出 CSV
        </el-button>
        <el-button
          :icon="DownloadIcon"
          size="default"
          @click="$emit('export-full')"
          :loading="exportLoading"
        >
          完整导出
        </el-button>
        <el-button
          type="primary"
          :icon="DownloadIcon"
          size="default"
          @click="$emit('export')"
          :loading="exportLoading"
        >
          导出 Excel
        </el-button>
      </div>
    </div>

    <div class="table-scroll">
      <el-table
        ref="tableRef"
        :data="rows"
        stripe
        border
        style="width: 100%"
        :row-class-name="rowClassName"
        empty-text="暂无识别结果"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="45" align="center" />
        <el-table-column type="index" label="#" width="55" align="center" />
        <el-table-column prop="filename" label="文件名" min-width="180" show-overflow-tooltip />
        <el-table-column prop="documentLabel" label="单据" width="80" align="center" />
        <el-table-column
          v-for="col in columns"
          :key="col"
          :prop="col"
          :label="col"
          min-width="160"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <div class="cell-with-conf" @click="copyCell(row.data[col], col)" style="cursor: pointer;" :title="'点击复制'">
              <span :class="getCellClass(row, col)">{{ row.data[col] ?? '-' }}</span>
              <el-tag
                v-if="row.fieldConfidence[col] !== undefined"
                :type="fieldConfType(row.fieldConfidence[col])"
                size="small"
                class="cell-conf-tag"
              >
                {{ (row.fieldConfidence[col] * 100).toFixed(0) }}%
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="100" align="center">
          <template #default="{ row }">
            <el-tag
              :type="confidenceType(row.confidence)"
              size="small"
              effect="plain"
            >
              {{ (row.confidence * 100).toFixed(0) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120" align="center">
          <template #default="{ row }">
            <div class="status-cell">
              <el-tag v-if="row.status === 'completed'" type="success" size="small">成功</el-tag>
              <el-tag v-else-if="row.status === 'failed'" type="danger" size="small">失败</el-tag>
              <el-tag v-else type="info" size="small">{{ row.status }}</el-tag>
              <span v-if="row.errorReason" class="status-error-text" :title="row.errorReason">
                {{ row.errorReason }}
              </span>
              <el-button
                v-if="row.status === 'failed'"
                size="small"
                type="warning"
                plain
                @click.stop="$emit('retry', row)"
              >重试</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Download as DownloadIcon } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  results: { type: Array, default: () => [] },
  showToolbar: { type: Boolean, default: true },
  exportLoading: { type: Boolean, default: false },
  retryAllLoading: { type: Boolean, default: false },
  totalResults: { type: Number, default: 0 },
  hasMoreResults: { type: Boolean, default: false },
  loadingMoreResults: { type: Boolean, default: false },
})

const emit = defineEmits(['export', 'export-csv', 'export-full', 'selection-change', 'retry-all', 'retry', 'load-more'])

const tableRef = ref(null)

function handleSelectionChange(selection) {
  emit('selection-change', selection)
}

function extractErrorReason(rawOcrText) {
  if (!rawOcrText) return ''
  if (rawOcrText.startsWith('OCR_ERROR:')) {
    return rawOcrText.replace('OCR_ERROR:', '').trim()
  }
  return ''
}

const rows = computed(() =>
  props.results.map((r) => {
    const rawData = r.structured_data ?? {}
    const flatData = {}
    const fieldConfidence = {}
    for (const [key, val] of Object.entries(rawData)) {
      if (typeof val === 'object' && val !== null && val.value !== undefined) {
        flatData[key] = val.value
        fieldConfidence[key] = val.confidence ?? 1.0
      } else {
        flatData[key] = String(val ?? '')
      }
    }
    const documentCount = r.source_document_count || 1
    const documentIndex = r.source_document_index || 1
    return {
      id: r.id,
      filename: r.filename,
      documentLabel: documentCount > 1 ? `${documentIndex}/${documentCount}` : '1',
      confidence: r.confidence ?? 0,
      status: r.status,
      lowFields: r.low_confidence_fields ?? [],
      data: flatData,
      fieldConfidence,
      errorReason: r.error_message || extractErrorReason(r.raw_ocr_text),
    }
  })
)

const failedCount = computed(() => rows.value.filter((r) => r.status === 'failed').length)

const resultCountText = computed(() => {
  if (props.totalResults > rows.value.length) {
    return `当前显示 ${rows.value.length} / ${props.totalResults} 条识别结果`
  }
  return `共 ${rows.value.length} 条识别结果`
})

const columns = computed(() => {
  const keySet = new Set()
  rows.value.forEach((r) => {
    Object.keys(r.data).forEach((k) => keySet.add(k))
  })
  const preferred = [
    '电子回单号码', '付款方户名', '付款方账号', '付款方开户行',
    '收款方户名', '收款方账号', '收款方开户行',
    '交易金额', '金额', '金额大写', '摘要', '用途',
    '业务种类', '业务产品种类', '交易流水号', '时间戳', '交易日期',
    '发票代码', '发票号码', '开票日期', '购买方名称', '销售方名称',
    '金额合计', '税额', '价税合计',
  ]
  const keys = Array.from(keySet)
  const ordered = preferred.filter((key) => keySet.has(key))
  ordered.push(...keys.filter((key) => !preferred.includes(key)).sort())
  return ordered
})

const lowConfidenceCount = computed(() => {
  let count = 0
  rows.value.forEach((r) => {
    count += r.lowFields.filter((field) => shouldMarkLowConfidence(r, field)).length
  })
  return count
})

function rowClassName({ row }) {
  return row.status === 'failed' ? 'row-failed' : ''
}

function getCellClass(row, col) {
  return shouldMarkLowConfidence(row, col) ? 'cell-low-confidence' : ''
}

function shouldMarkLowConfidence(row, col) {
  if (!row.lowFields.includes(col)) return false
  if (isReliableAmountField(row, col)) return false
  return true
}

function isReliableAmountField(row, col) {
  if (!isAmountField(col)) return false
  const value = row.data[col]
  if (!parseAmount(value)) return false
  return (row.fieldConfidence[col] ?? 0) >= 0.8
}

function isAmountField(col) {
  return ['交易金额', '金额', '金额小写', '价税合计', '金额合计', '税额', '月费', '付款金额', '转账金额'].some((token) => col.includes(token))
}

function parseAmount(value) {
  if (value === null || value === undefined || value === '') return ''
  const text = String(value)
    .replace(/[￥¥,元人民币港币]/g, '')
    .replace(/[−—]/g, '-')
    .trim()
  const match = text.match(/[+-]?\d+(?:\.\d{1,4})?/)
  return match ? match[0] : ''
}

function confidenceType(val) {
  if (val >= 0.8) return 'success'
  if (val >= 0.5) return 'warning'
  return 'danger'
}

function fieldConfType(val) {
  if (val >= 0.8) return 'success'
  if (val >= 0.5) return 'warning'
  return 'danger'
}

async function copyCell(value, fieldName) {
  if (!value || value === '-') return
  try {
    await navigator.clipboard.writeText(String(value))
    ElMessage.success(`已复制「${fieldName}」`)
  } catch {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
.result-table {
  background: var(--color-surface-card);
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--color-border);
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
}

.toolbar-info {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.toolbar-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.table-scroll {
  overflow-x: auto;
  padding: 0;
}

:deep(.cell-low-confidence) {
  color: var(--color-danger-text) !important;
  font-weight: 600;
}

:deep(.cell-low-confidence::before) {
  content: '';
  display: inline-block;
  position: absolute;
  top: 2px;
  right: 2px;
  bottom: 2px;
  left: 2px;
  background: var(--color-danger-bg);
  border-radius: 4px;
  z-index: 0;
}

:deep(.cell-low-confidence) {
  position: relative;
}

:deep(.row-failed) {
  background: rgba(239, 68, 68, 0.04) !important;
}

.failure-alert {
  margin: 12px 16px 0;
  border-radius: var(--radius-md);
}

/* ---- status cell ---- */
.status-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.status-error-text {
  font-size: 11px;
  color: var(--color-danger-text);
  line-height: 1.3;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

/* ---- cell with inline confidence tag ---- */
.cell-with-conf {
  display: flex;
  align-items: center;
  gap: 6px;
}

.cell-conf-tag {
  flex-shrink: 0;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 11px;
}
</style>
