<template>
  <div class="task-page">
    <div class="task-header">
      <h2 class="task-title">任务列表</h2>
      <div class="task-header__actions">
        <el-button
          :icon="DownloadIcon"
          :disabled="selectedExportableIds.length < 2"
          :loading="mergingExport"
          @click="handleMergedExport('standard')"
        >
          合并导出标准表
        </el-button>
        <el-button
          :icon="DownloadIcon"
          :disabled="selectedExportableIds.length < 2"
          :loading="mergingExport"
          @click="handleMergedExport('full')"
        >
          合并完整导出
        </el-button>
        <el-button type="primary" :icon="Plus" @click="$router.push('/')">
          新建任务
        </el-button>
      </div>
    </div>

    <div v-if="selectedJobIds.length" class="merge-bar">
      <span>已选择 {{ selectedJobIds.length }} 个任务，可合并导出 {{ selectedExportableIds.length }} 个</span>
      <el-button text type="primary" @click="clearSelection">清空选择</el-button>
    </div>

    <div class="task-list" v-loading="loading">
      <template v-if="jobs.length">
        <div
          v-for="job in jobs"
          :key="job.id"
          class="task-card"
          @click="goToResult(job)"
        >
          <div class="task-card__header">
            <div class="task-card__title">
              <el-checkbox
                :model-value="selectedJobIds.includes(job.id)"
                :disabled="!isExportable(job)"
                @click.stop
                @change="toggleJobSelection(job)"
              />
              <span class="task-id">{{ job.id }}</span>
            </div>
            <el-tag :type="statusTagType(job.status)" size="small" effect="dark">
              {{ statusLabel(job.status) }}
            </el-tag>
          </div>

          <div class="task-card__body">
            <div class="task-info">
              <span class="info-label">文件数</span>
              <span class="info-value">{{ job.processed_files }} / {{ job.total_files }}</span>
            </div>
            <div class="task-info task-info--stats" v-if="hasResultStats(job)">
              <span class="info-label">结果</span>
              <span class="info-value">
                成功 {{ job.completed_files }} · 失败 {{ job.failed_files }} · 未处理 {{ job.pending_files }}
              </span>
            </div>
            <div class="task-info" v-if="job.status === 'queued' && job.queue_position">
              <span class="info-label">队列</span>
              <span class="info-value">前面 {{ job.queue_position - 1 }} 个任务</span>
            </div>
            <div class="task-info" v-if="isTerminal(job.status)">
              <span class="info-label">耗时</span>
              <span class="info-value">{{ formatDuration(job.created_at, job.updated_at) }}</span>
            </div>
          </div>
          <div class="task-error" v-if="job.error_message">
            {{ job.error_message }}
          </div>

          <div class="task-card__footer">
            <span class="task-time">{{ formatTime(job.updated_at) }}</span>
            <div class="footer-actions">
              <el-button
                v-if="isExportable(job)"
                text
                type="primary"
                size="small"
                @click.stop="handleExport(job.id)"
                :loading="exportingId === job.id"
              >
                导出 Excel
              </el-button>
              <el-button
                v-if="isExportable(job)"
                text
                type="primary"
                size="small"
                @click.stop="handleExport(job.id, 'xlsx', false, 'full')"
                :loading="exportingId === job.id"
              >
                完整导出
              </el-button>
              <el-button
                v-else-if="hasResultStats(job)"
                text
                type="primary"
                size="small"
                @click.stop="handleExport(job.id, 'csv', true)"
                :loading="exportingId === job.id"
              >
                导出当前 CSV
              </el-button>
              <el-button
                v-if="canRetryUnfinished(job)"
                text
                type="warning"
                size="small"
                @click.stop="handleRetry(job)"
                :loading="retryingId === job.id"
              >
                重试未完成
              </el-button>
              <el-button
                text
                type="danger"
                size="small"
                @click.stop="handleDelete(job.id)"
                :icon="Delete"
              >
                删除
              </el-button>
            </div>
          </div>
        </div>
      </template>

      <el-empty v-else description="还没有任务记录">
        <el-button type="primary" @click="$router.push('/')">
          去上传第一份文件
        </el-button>
      </el-empty>
    </div>

    <div v-if="hasMore" class="pagination-footer">
      <el-button @click="loadMore" :loading="loading" plain>
        加载更多 ({{ totalLoaded }} 条)
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Delete, Download as DownloadIcon } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listJobs, downloadExcel, downloadMergedStandardExport, deleteJob, retryUnfinished } from '../api'

const router = useRouter()

const jobs = ref([])
const loading = ref(false)
const exportingId = ref(null)
const retryingId = ref(null)
const mergingExport = ref(false)
const selectedJobIds = ref([])
const page = ref(0)
const hasMore = ref(true)
const totalLoaded = ref(0)

const PAGE_SIZE = 20

const selectedExportableIds = computed(() => {
  const exportable = new Set(jobs.value.filter(isExportable).map((job) => job.id))
  return selectedJobIds.value.filter((jobId) => exportable.has(jobId))
})

async function fetchJobs(append = false) {
  loading.value = true
  try {
    const res = await listJobs({ limit: PAGE_SIZE, offset: page.value * PAGE_SIZE })
    const newJobs = res.data
    if (append) {
      jobs.value = [...jobs.value, ...newJobs]
    } else {
      jobs.value = newJobs
    }
    totalLoaded.value = jobs.value.length
    hasMore.value = newJobs.length === PAGE_SIZE
  } catch {
    jobs.value = []
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  page.value++
  await fetchJobs(true)
}

function goToResult(job) {
  router.push({ name: 'Result', params: { jobId: job.id } })
}

async function handleExport(jobId, format = 'xlsx', includePartial = false, detail = 'standard') {
  exportingId.value = jobId
  try {
    const res = await downloadExcel(jobId, '', format, includePartial, detail)
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const link = document.createElement('a')
    link.href = url
    const contentType = res.headers?.['content-type'] || ''
    const exportExtension = format === 'csv' && contentType.includes('zip') ? 'zip' : format
    link.setAttribute('download', `识别结果_${jobId}.${exportExtension}`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success(exportExtension === 'zip' ? 'CSV 压缩包已下载' : (format === 'csv' ? 'CSV 已下载' : (detail === 'full' ? '完整 Excel 已下载' : '标准 Excel 已下载')))
  } catch {
    ElMessage.error('导出失败，请重试')
  } finally {
    exportingId.value = null
  }
}

async function handleMergedExport(detail = 'standard') {
  if (selectedExportableIds.value.length < 2 || mergingExport.value) return
  mergingExport.value = true
  try {
    const res = await downloadMergedStandardExport(selectedExportableIds.value, 'xlsx', false, detail)
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `合并识别结果_${detail === 'full' ? '完整_' : ''}${new Date().toISOString().slice(0, 10)}.xlsx`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success(`已合并导出 ${selectedExportableIds.value.length} 个任务`)
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '合并导出失败，请重试')
  } finally {
    mergingExport.value = false
  }
}

function toggleJobSelection(job) {
  if (!isExportable(job)) return
  if (selectedJobIds.value.includes(job.id)) {
    selectedJobIds.value = selectedJobIds.value.filter((id) => id !== job.id)
  } else {
    selectedJobIds.value = [...selectedJobIds.value, job.id]
  }
}

function clearSelection() {
  selectedJobIds.value = []
}

async function handleDelete(jobId) {
  try {
    await ElMessageBox.confirm('确定要删除该任务及其所有数据吗？', '删除确认', {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteJob(jobId)
    ElMessage.success('任务已删除')
    fetchJobs()
  } catch {
    // User cancelled or delete failed
  }
}

async function handleRetry(job) {
  retryingId.value = job.id
  try {
    const res = await retryUnfinished(job.id)
    ElMessage.success(`已重新排队 ${res.data.count} 个未完成文件`)
    page.value = 0
    await fetchJobs()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '重试失败，请稍后再试')
  } finally {
    retryingId.value = null
  }
}

function statusTagType(status) {
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
  return map[status] || 'info'
}

function statusLabel(status) {
  const map = {
    uploaded: '已上传',
    queued: '排队中',
    pending: '等待',
    processing: '处理中',
    completed: '完成',
    partial_failed: '部分失败',
    timeout_partial: '超时',
    failed: '失败',
  }
  return map[status] || status
}

function isTerminal(status) {
  return ['completed', 'partial_failed', 'timeout_partial', 'failed'].includes(status)
}

function isExportable(job) {
  return ['completed', 'partial_failed', 'timeout_partial'].includes(job.status) && job.processed_files > 0
}

function canRetryUnfinished(job) {
  const unfinished = (job.failed_files || 0) + (job.pending_files || 0)
  return ['failed', 'partial_failed', 'timeout_partial'].includes(job.status) && unfinished > 0
}

function hasResultStats(job) {
  return (job.completed_files || 0) + (job.failed_files || 0) + (job.pending_files || 0) > 0
}

function templateLabel(type) {
  const map = {
    invoice: '增值税发票',
    receipt: '收据',
    bank_receipt: '银行回单',
    general: '通用票据',
  }
  return map[type] || type
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatDuration(startIso, endIso) {
  if (!startIso || !endIso) return '-'
  const start = new Date(startIso).getTime()
  const end = new Date(endIso).getTime()
  const diff = Math.round((end - start) / 1000)
  if (diff < 60) return `${diff}秒`
  const mins = Math.floor(diff / 60)
  const secs = diff % 60
  return `${mins}分${secs}秒`
}

onMounted(() => {
  fetchJobs()
})
</script>

<style scoped>
.task-page {
  max-width: 900px;
  margin: 0 auto;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.task-header__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.task-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 200px;
}

.merge-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  padding: 10px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-card);
  color: var(--color-text-secondary);
  font-size: 13px;
}

.task-card {
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.task-card:hover {
  border-color: var(--color-primary-light);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.task-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.task-card__title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.task-id {
  font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary);
  background: rgba(79, 70, 229, 0.06);
  padding: 2px 10px;
  border-radius: 4px;
}

.task-card__body {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  margin-bottom: 10px;
}

.task-info {
  display: flex;
  align-items: center;
  gap: 6px;
}

.info-label {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.info-value {
  font-size: 13px;
  color: var(--color-text);
  font-weight: 500;
}

.info-value--truncate {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-info--stats {
  min-width: 260px;
}

.task-error {
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.task-card__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.footer-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.task-time {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.pagination-footer {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}
</style>
