<template>
  <div class="result-page">
    <div class="result-header">
      <div class="result-title-row">
        <el-button text :icon="BackIcon" @click="$router.push('/tasks')">返回任务列表</el-button>
        <h2 class="result-title">识别结果</h2>
        <span class="result-job-id">任务 ID: {{ jobId }}</span>
      </div>
      <div class="result-search" v-if="results.length > 0">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索文件名、字段值..."
          :prefix-icon="SearchIcon"
          clearable
          size="default"
          class="search-input"
        />
      </div>
    </div>

    <el-alert
      v-if="errorMsg"
      :title="errorMsg"
      type="error"
      :closable="false"
      show-icon
      class="result-alert"
    />

    <ProgressTracker
      v-if="jobStatus"
      :total="jobStatus.total_files"
      :processed="jobStatus.processed_files"
      :status="jobStatus.status"
      :error-message="jobStatus.error_message"
      :eta-seconds="jobStatus.eta_seconds"
      :queue-eta-seconds="jobStatus.queue_eta_seconds"
      :queue-ahead-count="jobStatus.queue_ahead_count"
    />

    <div v-if="batchChildren.length" class="batch-panel">
      <div class="batch-panel__header">
        <div>
          <div class="batch-panel__title">批次进度</div>
          <div class="batch-panel__meta">
            共 {{ batchSummary.total_batches }} 批 · 处理中 {{ batchSummary.active_batches }} · 排队 {{ batchSummary.queued_batches }} · 完成 {{ batchSummary.completed_batches }}
          </div>
        </div>
        <el-button
          size="small"
          :icon="DownloadIcon"
          @click="handleExport('csv', true)"
          :loading="exporting"
        >
          导出当前 CSV
        </el-button>
      </div>
      <div class="batch-grid">
        <div
          v-for="child in batchChildren"
          :key="child.id"
          class="batch-item"
          :class="`batch-item--${child.status}`"
        >
          <span class="batch-item__index">#{{ child.batch_index }}</span>
          <span class="batch-item__status">{{ statusLabel(child.status) }}</span>
          <span class="batch-item__progress">{{ child.processed_files }} / {{ child.total_files }}</span>
        </div>
      </div>
    </div>

    <div v-if="showLivePanel" class="live-panel">
      <div class="live-panel__header">
        <div>
          <div class="live-panel__title">实时产出</div>
          <div class="live-panel__meta">
            成功 {{ jobStatus?.completed_files || 0 }} · 失败 {{ jobStatus?.failed_files || 0 }} · 等待 {{ jobStatus?.pending_files || 0 }}
          </div>
        </div>
        <div class="live-panel__actions">
          <el-button size="small" :loading="livePreviewLoading" @click="fetchLivePreview({ force: true })">
            刷新
          </el-button>
          <el-button
            size="small"
            :icon="DownloadIcon"
            @click="handleExport('csv', true)"
            :loading="exporting"
          >
            导出当前 CSV
          </el-button>
        </div>
      </div>

      <div class="live-columns">
        <div class="live-column">
          <div class="live-column__title">最近完成</div>
          <div v-if="recentCompleted.length" class="live-list">
            <div v-for="item in recentCompleted" :key="item.id" class="live-row">
              <div class="live-row__main">
                <span class="live-row__file" :title="item.filename">{{ item.filename }}</span>
                <el-tag
                  v-if="(item.source_document_count || 1) > 1"
                  size="small"
                  effect="plain"
                >
                  {{ item.source_document_index }}/{{ item.source_document_count }}
                </el-tag>
              </div>
              <div class="live-row__fields">
                <span>{{ fieldValue(item, ['交易日期', '日期', '时间戳', '交易时间']) }}</span>
                <span>{{ fieldValue(item, ['金额', '交易金额', '金额小写', '付款金额']) }}</span>
                <span>{{ fieldValue(item, ['付款方户名', '付款人户名', '付款方', '付款人']) }}</span>
                <span>{{ fieldValue(item, ['收款方户名', '收款人户名', '收款方', '收款人']) }}</span>
              </div>
            </div>
          </div>
          <div v-else class="live-empty">还没有完成结果</div>
        </div>

        <div class="live-column live-column--failed">
          <div class="live-column__title">最近失败</div>
          <div v-if="recentFailed.length" class="live-list">
            <div v-for="item in recentFailed" :key="item.id" class="live-row live-row--failed">
              <div class="live-row__main">
                <span class="live-row__file" :title="item.filename">{{ item.filename }}</span>
                <el-tag size="small" type="danger" effect="plain">失败</el-tag>
              </div>
              <div class="live-row__error">{{ resultError(item) || '识别失败，等待查看详情' }}</div>
            </div>
          </div>
          <div v-else class="live-empty">暂无失败结果</div>
        </div>
      </div>
    </div>

    <!-- 左右分栏布局 -->
    <div v-if="results.length > 0" class="result-split">
        <!-- 左侧：文件列表 + 预览 -->
      <div class="preview-panel">
        <div class="file-list">
          <div
            v-for="(item, idx) in results"
            :key="item.id"
            class="file-item"
            :class="{ 'file-item--active': selectedFile?.id === item.id }"
            @click="selectFile(item)"
          >
            <span class="file-item__index">{{ idx + 1 }}</span>
            <span class="file-item__name" :title="item.filename">{{ item.filename }}</span>
            <span
              v-if="(item.source_document_count || 1) > 1"
              class="file-item__doc-index"
            >
              {{ item.source_document_index }}/{{ item.source_document_count }}
            </span>
            <el-tag
              v-if="item.status === 'completed'"
              type="success"
              size="small"
              effect="plain"
              class="file-item__status"
            >✓</el-tag>
            <el-tag
              v-else-if="item.status === 'failed'"
              type="danger"
              size="small"
              effect="plain"
              class="file-item__status"
            >✕</el-tag>
          </div>
        </div>

        <div class="preview-area">
          <template v-if="selectedFile">
            <div class="preview-wrapper">
              <el-image
                v-if="isImage(selectedFile.filename)"
                :src="getFileUrl(selectedFile.filename)"
                :preview-src-list="imagePreviewList"
                :initial-index="selectedFileIndex"
                fit="contain"
                class="preview-image"
                :alt="selectedFile.filename"
              />
              <iframe
                v-else-if="isPdf(selectedFile.filename)"
                :src="getFileUrl(selectedFile.filename)"
                class="preview-pdf"
              />
              <div v-else class="preview-placeholder">
                <el-icon :size="48"><Document /></el-icon>
                <p>不支持预览此文件类型</p>
              </div>
              <el-button
                class="preview-fullscreen-btn"
                size="small"
                :icon="FullScreen"
                circle
                @click="openFullscreen"
                title="全屏查看"
              />
            </div>
          </template>
          <div v-else class="preview-placeholder">
            <el-icon :size="48"><View /></el-icon>
            <p>点击左侧文件查看原图</p>
          </div>
        </div>
      </div>

      <!-- 全屏预览 -->
      <Teleport to="body">
        <div v-if="fullscreenVisible" class="fullscreen-overlay" @click.self="fullscreenVisible = false">
          <div class="fullscreen-viewer">
            <div class="fullscreen-header">
              <span class="fullscreen-filename">{{ selectedFile?.filename }}</span>
              <el-button text :icon="Close" @click="fullscreenVisible = false" class="fullscreen-close-btn" />
            </div>
            <div class="fullscreen-body">
              <el-image
                v-if="isImage(selectedFile?.filename)"
                :src="getFileUrl(selectedFile.filename)"
                :preview-src-list="imagePreviewList"
                :initial-index="selectedFileIndex"
                fit="contain"
                class="fullscreen-image"
              />
              <iframe
                v-else-if="isPdf(selectedFile?.filename)"
                :src="getFileUrl(selectedFile.filename)"
                class="fullscreen-pdf"
              />
              <div v-else class="preview-placeholder">
                <el-icon :size="48"><Document /></el-icon>
                <p>不支持预览此文件类型</p>
              </div>
            </div>
          </div>
        </div>
      </Teleport>

      <!-- 右侧：识别结果 -->
      <div class="results-panel">
        <el-tabs v-model="activeTypeTab" class="result-tabs type-tabs">
          <el-tab-pane
            v-for="(items, docType) in groupedResults"
            :key="docType"
            :label="`${typeLabel(docType)} (${items.length})`"
            :name="docType"
          >
            <el-tabs v-model="activeViewTab" class="view-tabs">
              <el-tab-pane label="表格视图" name="table">
                <ResultTable
                  :results="items"
                  :export-loading="exporting"
                  :retry-all-loading="retryAllLoading"
                  :total-results="totalResults"
                  :has-more-results="hasMoreResults"
                  :loading-more-results="loadingMoreResults"
                  @export="handleExport"
                  @export-csv="handleCsvExport"
                  @export-full="handleFullExport"
                  @load-more="loadMoreResults"
                  @retry="retrySingle"
                  @retry-all="retryAll"
                />
              </el-tab-pane>

              <el-tab-pane name="json">
                <template #label>
                  <span>JSON 视图</span>
                </template>

                <div class="json-toolbar">
                  <span class="json-summary">
                    共 {{ items.length }} 条识别结果
                  </span>
                  <el-button
                    size="small"
                    :icon="CopyDocument"
                    :type="copied ? 'success' : 'default'"
                    @click="copyJson"
                  >
                    {{ copied ? '已复制' : '复制 JSON' }}
                  </el-button>
                </div>

                <div
                  v-for="(item, idx) in items"
                  :key="idx"
                  class="json-card"
                  :class="{ 'is-failed': item.status === 'failed' }"
                >
                  <div class="json-card-header">
                    <div class="json-card-filename">
                      <span class="json-card-index">#{{ idx + 1 }}</span>
                      <span>{{ item.filename }}</span>
                      <el-tag
                        v-if="(item.source_document_count || 1) > 1"
                        size="small"
                        effect="plain"
                      >
                        单据 {{ item.source_document_index }}/{{ item.source_document_count }}
                      </el-tag>
                    </div>
                    <div class="json-card-badges">
                      <el-tag
                        v-if="item.status === 'completed'"
                        type="success"
                        size="small"
                        effect="plain"
                      >成功</el-tag>
                      <el-tag
                        v-else-if="item.status === 'failed'"
                        type="danger"
                        size="small"
                        effect="plain"
                      >失败</el-tag>
                      <el-tag
                        v-else
                        type="info"
                        size="small"
                        effect="plain"
                      >{{ item.status }}</el-tag>
                      <el-tag
                        :type="confidenceTagType(item.confidence)"
                        size="small"
                        effect="plain"
                      >
                        置信度 {{ (item.confidence * 100).toFixed(0) }}%
                      </el-tag>
                      <el-button
                        v-if="item.status === 'failed'"
                        size="small"
                        type="warning"
                        plain
                        @click="retrySingle(item.id)"
                      >重试</el-button>
                    </div>
                  </div>

                  <el-alert
                    v-if="item.status === 'failed' && resultError(item)"
                    :title="resultError(item)"
                    type="error"
                    :closable="false"
                    show-icon
                    class="json-failure-reason"
                  />

                  <div class="json-section">
                    <div class="json-section-title">OCR 原始识别文本</div>
                    <div v-if="extractOcrError(item.raw_ocr_text)" class="ocr-error-text">
                      <el-icon><Warning /></el-icon>
                      <span>{{ extractOcrError(item.raw_ocr_text) }}</span>
                    </div>
                    <div v-else class="ocr-line-tags">
                      <el-tag
                        v-for="(line, li) in ocrLines(item.raw_ocr_text)"
                        :key="li"
                        size="small"
                        class="ocr-line-tag"
                      >{{ line }}</el-tag>
                      <span v-if="!ocrLines(item.raw_ocr_text).length" class="json-empty">（无 OCR 文本）</span>
                    </div>
                  </div>

                  <div class="json-section">
                    <div class="json-section-title">结构化数据</div>
                    <div class="struct-fields">
                      <div
                        v-for="(val, key) in item.structured_data"
                        :key="key"
                        class="struct-field"
                        :class="{ 'is-low-confidence': isLowConfidence(item, key) }"
                      >
                        <span class="struct-label">{{ key }}</span>
                        <span class="struct-sep">:</span>
                        <span class="struct-value">{{ displayValue(val) }}</span>
                        <span v-if="confidenceOf(val) !== null" class="struct-confidence">
                          {{ confidenceOf(val) }}%
                        </span>
                      </div>
                      <span v-if="!Object.keys(item.structured_data || {}).length" class="json-empty">
                        {{ item.status === 'failed' ? '（识别失败，无结构化数据）' : '（无结构化数据）' }}
                      </span>
                    </div>
                  </div>
                </div>

                <div class="json-raw-section">
                  <div class="json-section-title">原始数据 JSON</div>
                  <pre class="json-viewer"><code v-html="highlightedJson"></code></pre>
                </div>
              </el-tab-pane>
            </el-tabs>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <div v-if="jobStatus?.status === 'queued' || jobStatus?.status === 'processing'" class="result-waiting">
      <el-icon class="is-loading" :size="24"><Loading /></el-icon>
      <div class="result-waiting__copy">
        <span class="result-waiting__title">{{ waitingTitle }}</span>
        <span v-if="waitingEstimate" class="result-waiting__meta">{{ waitingEstimate }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Back as BackIcon, Loading, CopyDocument, Warning, Search as SearchIcon, Document, View, FullScreen, Close, Download as DownloadIcon } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ProgressTracker from '../components/ProgressTracker.vue'
import ResultTable from '../components/ResultTable.vue'
import {
  getJobStatus,
  getJobBatches,
  getJobResultsSummary,
  getJobRecentResults,
  getJobResultDetail,
  downloadExcel,
  retryAll as retryAllApi,
  retrySingle as retrySingleApi,
  createJobStream,
} from '../api'

const route = useRoute()
const jobId = route.params.jobId
const RESULT_PAGE_SIZE = 500

const jobStatus = ref(null)
const results = ref([])
const errorMsg = ref('')
const exporting = ref(false)
const loadingMoreResults = ref(false)
const totalResults = ref(0)
const resultOffset = ref(0)
const hasMoreResults = ref(false)
const activeTypeTab = ref('')
const activeViewTab = ref('table')
const copied = ref(false)
const searchKeyword = ref('')
const selectedFile = ref(null)
const fullscreenVisible = ref(false)
const detailCache = ref(new Map())
const batchSummary = ref({})
const batchChildren = ref([])
const recentCompleted = ref([])
const recentFailed = ref([])
const livePreviewLoading = ref(false)
let lastLivePreviewAt = 0

async function selectFile(item) {
  selectedFile.value = item
  await ensureResultDetail(item.id)
}

function openFullscreen() {
  fullscreenVisible.value = true
}

function isImage(filename) {
  return /\.(png|jpg|jpeg|bmp|tiff|tif|webp)$/i.test(filename)
}

function isPdf(filename) {
  return /\.pdf$/i.test(filename)
}

function getFileUrl(filename) {
  const sid = localStorage.getItem('session_id') || ''
  return `/api/upload/${jobId}/${filename}?session_id=${sid}`
}

const imagePreviewList = ref([])
const imagePreviewListComputed = computed(() => {
  return results.value
    .filter(r => isImage(r.filename))
    .map(r => getFileUrl(r.filename))
})

function refreshImagePreviewList() {
  imagePreviewList.value = imagePreviewListComputed.value
}

// 当前选中文件在图片列表中的索引
const selectedFileIndex = computed(() => {
  if (!selectedFile.value) return 0
  const images = results.value.filter(r => isImage(r.filename))
  return images.findIndex(r => r.id === selectedFile.value.id)
})

let pollTimer = null
let pollRetryTimers = new Set()
let resultsLoaded = ref(false)
let eventSource = null

async function fetchStatus() {
  try {
    const res = await getJobStatus(jobId)
    jobStatus.value = res.data
    fetchBatchSummary()
    fetchLivePreview()

    if (isTerminalStatus(res.data.status)) {
      stopPolling()
      if (!resultsLoaded.value) {
        await fetchResults()
        resultsLoaded.value = true
      }
      triggerNotification(res.data.status)
    }
  } catch (err) {
    errorMsg.value = err.response?.data?.detail || '获取任务状态失败'
    stopPolling()
  }
}

function startSSE() {
  stopPolling()
  // 先获取当前状态，确保 ProgressTracker 能显示处理中
  fetchStatus()

  const sessionId = localStorage.getItem('session_id') || ''
  eventSource = createJobStream(jobId, sessionId)

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data)
    jobStatus.value = { ...jobStatus.value, ...data }
    fetchBatchSummary()
    fetchLivePreview()

    if (isTerminalStatus(data.status)) {
      eventSource.close()
      eventSource = null
      if (!resultsLoaded.value) {
        fetchResults().then(() => { resultsLoaded.value = true })
      }
      triggerNotification(data.status)
    }
  }

  eventSource.onerror = () => {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    // 降级为轮询
    pollTimer = setInterval(fetchStatus, 3000)
  }
}

async function fetchBatchSummary() {
  try {
    const res = await getJobBatches(jobId)
    batchSummary.value = res.data || {}
    batchChildren.value = res.data?.children || []
  } catch {
    batchSummary.value = {}
    batchChildren.value = []
  }
}

const showLivePanel = computed(() => {
  const status = jobStatus.value?.status
  return ['queued', 'processing'].includes(status) || recentCompleted.value.length > 0 || recentFailed.value.length > 0
})

async function fetchLivePreview({ force = false } = {}) {
  const status = jobStatus.value?.status
  const active = ['queued', 'processing'].includes(status)
  if (!force && !active) return
  if (livePreviewLoading.value) return
  const now = Date.now()
  if (!force && now - lastLivePreviewAt < 5000) return
  lastLivePreviewAt = now
  livePreviewLoading.value = true
  try {
    const [completedRes, failedRes] = await Promise.all([
      getJobRecentResults(jobId, { limit: 20, status: 'completed' }),
      getJobRecentResults(jobId, { limit: 8, status: 'failed' }),
    ])
    recentCompleted.value = completedRes.data?.results || []
    recentFailed.value = failedRes.data?.results || []
    if (completedRes.data?.job) {
      jobStatus.value = { ...jobStatus.value, ...completedRes.data.job }
    }
  } catch {
    // Live preview is best effort; status polling still drives the page.
  } finally {
    livePreviewLoading.value = false
  }
}

function triggerNotification(status) {
  if (!('Notification' in window)) return
  const title = status === 'completed' ? '识别完成' : '识别结束'
  const body = status === 'completed' ? '点击查看识别结果' : '部分文件处理失败或超时，请查看详情'
  if (Notification.permission === 'granted') {
    new Notification(title, { body })
  } else if (Notification.permission !== 'denied') {
    Notification.requestPermission().then((perm) => {
      if (perm === 'granted') {
        new Notification(title, { body })
      }
    })
  }
}

function isTerminalStatus(status) {
  return ['completed', 'partial_failed', 'timeout_partial', 'failed'].includes(status)
}

async function fetchResults({ reset = true } = {}) {
  try {
    if (reset) {
      resultOffset.value = 0
    }
    const res = await getJobResultsSummary(jobId, {
      limit: RESULT_PAGE_SIZE,
      offset: resultOffset.value,
    })
    if (res.data.job) {
      jobStatus.value = res.data.job
    }
    const pageResults = res.data.results || []
    if (reset) {
      results.value = pageResults
    } else {
      const seenIds = new Set(results.value.map((item) => item.id))
      results.value = [
        ...results.value,
        ...pageResults.filter((item) => !seenIds.has(item.id)),
      ]
    }
    totalResults.value = res.data.total_results || results.value.length
    resultOffset.value = (res.data.offset || 0) + pageResults.length
    hasMoreResults.value = Boolean(res.data.has_more)
    mergeCachedDetails()
    refreshImagePreviewList()
    const types = [...new Set(results.value.map(r => r.document_type || 'unknown'))]
    if (types.length && (!activeTypeTab.value || !types.includes(activeTypeTab.value))) {
      activeTypeTab.value = types[0]
    }
    if (selectedFile.value && !results.value.some((item) => item.id === selectedFile.value.id)) {
      selectedFile.value = null
    }
    if (!selectedFile.value && results.value.length) {
      selectedFile.value = results.value[0]
      ensureResultDetail(selectedFile.value.id)
    }
  } catch (err) {
    errorMsg.value = err.response?.data?.detail || '获取结果失败'
  }
}

async function loadMoreResults() {
  if (loadingMoreResults.value || !hasMoreResults.value) return
  loadingMoreResults.value = true
  try {
    await fetchResults({ reset: false })
  } finally {
    loadingMoreResults.value = false
  }
}

async function ensureResultDetail(resultId) {
  if (!resultId || detailCache.value.has(resultId)) return
  try {
    const res = await getJobResultDetail(jobId, resultId)
    const next = new Map(detailCache.value)
    next.set(resultId, res.data)
    detailCache.value = next
    mergeCachedDetails()
  } catch {
    // Detail loading is opportunistic; summary data is still usable.
  }
}

function mergeCachedDetails() {
  if (!detailCache.value.size) return
  results.value = results.value.map((item) => detailCache.value.get(item.id) || item)
  if (selectedFile.value) {
    selectedFile.value = detailCache.value.get(selectedFile.value.id) || selectedFile.value
  }
}

const groupedResults = computed(() => {
  const groups = {}
  const keyword = searchKeyword.value.toLowerCase()
  results.value.forEach(r => {
    const type = r.document_type || 'unknown'
    if (keyword) {
      const match = r.filename.toLowerCase().includes(keyword) ||
        JSON.stringify(r.structured_data).toLowerCase().includes(keyword)
      if (!match) return
    }
    groups[type] = groups[type] || []
    groups[type].push(r)
  })
  return groups
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

const waitingTitle = computed(() => {
  return jobStatus.value?.status === 'queued'
    ? '任务正在排队，请稍候...'
    : 'AI 正在分析票据内容，请稍候...'
})

const waitingEstimate = computed(() => {
  const job = jobStatus.value
  if (!job) return ''
  if (job.status === 'queued') {
    const ahead = Number.isInteger(job.queue_ahead_count)
      ? job.queue_ahead_count
      : Math.max(0, (job.queue_position || 1) - 1)
    const eta = formatDuration(job.queue_eta_seconds)
    if (eta && ahead > 0) return `前面 ${ahead} 个任务，预计 ${eta} 后开始`
    if (eta) return `当前排在最前，预计 ${eta} 后开始`
    if (ahead > 0) return `前面还有 ${ahead} 个任务`
    return '当前排在最前，等待 worker 空闲'
  }
  if (job.status === 'processing') {
    const eta = formatDuration(job.eta_seconds)
    if (eta) return `预计剩余 ${eta}`
  }
  return ''
})

const TYPE_LABELS = {
  invoice: '增值税发票',
  receipt: '收据',
  bank_receipt: '银行回单',
  unknown: '其他票据',
}

function typeLabel(type) {
  return TYPE_LABELS[type] || type
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

function startPolling() {
  stopPolling()
  startSSE()
}

function stopPolling() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  // 清理所有重试定时器
  pollRetryTimers.forEach(timer => clearInterval(timer))
  pollRetryTimers.clear()
}

async function handleExport(format = 'xlsx', includePartial = false, detail = 'standard') {
  exporting.value = true
  try {
    const res = await downloadExcel(jobId, '', format, includePartial, detail)
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const link = document.createElement('a')
    const contentType = res.headers?.['content-type'] || ''
    const exportExtension = format === 'csv' && contentType.includes('zip') ? 'zip' : format
    link.href = url
    link.setAttribute('download', `识别结果_${jobId}.${exportExtension}`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success(exportExtension === 'zip' ? 'CSV 压缩包已下载' : (format === 'csv' ? 'CSV 已下载' : (detail === 'full' ? '完整 Excel 已下载' : '标准 Excel 已下载')))
  } catch (err) {
    errorMsg.value = err.response?.data?.detail || '导出失败'
    ElMessage.error('导出失败，请重试')
  } finally {
    exporting.value = false
  }
}

function handleCsvExport() {
  return handleExport('csv')
}

function handleFullExport() {
  return handleExport('xlsx', false, 'full')
}

// ---- JSON view helpers ----

function ocrLines(rawText) {
  if (!rawText) return []
  return rawText.split('\n').filter(Boolean)
}

function extractOcrError(rawText) {
  if (!rawText) return ''
  if (rawText.startsWith('OCR_ERROR:')) {
    return rawText.replace('OCR_ERROR:', '').trim()
  }
  return ''
}

function resultError(item) {
  return item?.error_message || extractOcrError(item?.raw_ocr_text || '')
}

function displayValue(val) {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'object' && val.value !== undefined) return val.value ?? '-'
  return String(val)
}

function fieldValue(item, keys) {
  const data = item?.structured_data || {}
  for (const key of keys) {
    if (data[key] === undefined || data[key] === null || data[key] === '') continue
    const value = displayValue(data[key])
    if (value && value !== '-') return value
  }
  return '-'
}

function confidenceOf(val) {
  if (typeof val === 'object' && val !== null && val.confidence !== undefined) {
    return (val.confidence * 100).toFixed(0)
  }
  return null
}

function isLowConfidence(item, key) {
  const fields = item.low_confidence_fields || []
  if (!fields.includes(key)) return false
  if (isReliableAmountValue(item, key)) return false
  return true
}

function isReliableAmountValue(item, key) {
  if (!isAmountFieldName(key)) return false
  const fieldData = item?.structured_data?.[key]
  const value = displayValue(fieldData)
  if (!parseAmount(value)) return false
  const confidence = typeof fieldData === 'object' && fieldData !== null
    ? Number(fieldData.confidence ?? 0)
    : 0
  return confidence >= 0.8
}

function isAmountFieldName(key) {
  return ['交易金额', '金额', '金额小写', '价税合计', '金额合计', '税额', '月费', '付款金额', '转账金额'].some((token) => key.includes(token))
}

function parseAmount(value) {
  if (value === null || value === undefined || value === '' || value === '-') return ''
  const text = String(value)
    .replace(/[￥¥,元人民币港币]/g, '')
    .replace(/[−—]/g, '-')
    .trim()
  const match = text.match(/[+-]?\d+(?:\.\d{1,4})?/)
  return match ? match[0] : ''
}

function confidenceTagType(val) {
  if (val >= 0.8) return 'success'
  if (val >= 0.5) return 'warning'
  return 'danger'
}

// ---- JSON syntax highlight ----

const currentTypeResults = computed(() => {
  return groupedResults.value[activeTypeTab.value] || []
})

const highlightedJson = computed(() => {
  const data = {
    job: jobStatus.value || { id: jobId },
    results: currentTypeResults.value,
  }
  const jsonStr = JSON.stringify(data, null, 2)
  return syntaxHighlight(jsonStr)
})

function syntaxHighlight(json) {
  const escaped = json
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  return escaped.replace(
    /("(\\u[\da-fA-F]{4}|\\[^u]|[^"\\])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    (match) => {
      let cls = 'json-number'
      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          cls = 'json-key'
        } else {
          cls = 'json-string'
        }
      } else if (/true|false/.test(match)) {
        cls = 'json-boolean'
      } else if (/null/.test(match)) {
        cls = 'json-null'
      }
      return `<span class="${cls}">${match}</span>`
    }
  )
}

const retryingIds = ref(new Set())
const retryAllLoading = ref(false)

async function retryAll() {
  if (retryAllLoading.value) return
  retryAllLoading.value = true
  try {
    const res = await retryAllApi(jobId)
    ElMessage.success(`已开始重试 ${res.data.count} 个文件，正在处理...`)
    await fetchResults()
    const pollRetry = setInterval(async () => {
      await fetchResults()
      const hasPending = results.value.some(r => r.status === 'pending')
      if (!hasPending) {
        clearInterval(pollRetry)
        pollRetryTimers.delete(pollRetry)
        ElMessage.success('全部重试完成')
      }
    }, 3000)
    pollRetryTimers.add(pollRetry)
  } catch (err) {
    const detail = err.response?.data?.detail || err.message || '批量重试失败'
    ElMessage.error(detail)
  } finally {
    retryAllLoading.value = false
  }
}

async function retrySingle(resultId) {
  if (typeof resultId === 'object' && resultId !== null) {
    resultId = resultId.id
  }
  if (retryingIds.value.has(resultId)) return
  retryingIds.value = new Set(retryingIds.value).add(resultId)
  try {
    await retrySingleApi(jobId, resultId)
    ElMessage.success('已开始重试')
    // 轮询直到结果不再为 pending
    const pollRetry = setInterval(async () => {
      await fetchResults()
      const item = results.value.find(r => r.id === resultId)
      if (item && item.status !== 'pending') {
        clearInterval(pollRetry)
        pollRetryTimers.delete(pollRetry)
        retryingIds.value = new Set([...retryingIds.value].filter(id => id !== resultId))
        if (item.status === 'completed') {
          ElMessage.success('重试成功')
        } else {
          ElMessage.error('重试失败')
        }
      }
    }, 2000)
    pollRetryTimers.add(pollRetry)
  } catch (err) {
    ElMessage.error(err.message || '重试失败')
    retryingIds.value = new Set([...retryingIds.value].filter(id => id !== resultId))
  }
}

async function copyJson() {
  try {
    const data = {
      job: jobStatus.value || { id: jobId },
      results: currentTypeResults.value,
    }
    const jsonStr = JSON.stringify(data, null, 2)
    await navigator.clipboard.writeText(jsonStr)
    copied.value = true
    ElMessage.success('JSON 已复制到剪贴板')
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

onMounted(() => {
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.result-page {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 左右分栏布局 */
.result-split {
  display: flex;
  gap: 20px;
  min-height: 600px;
}

.preview-panel {
  width: 380px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.file-list {
  max-height: 200px;
  overflow-y: auto;
  border-bottom: 1px solid var(--color-border);
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s ease;
  border-bottom: 1px solid var(--color-border);
}

.file-item:last-child {
  border-bottom: none;
}

.file-item:hover {
  background: rgba(79, 70, 229, 0.04);
}

.file-item--active {
  background: rgba(79, 70, 229, 0.08);
  border-left: 3px solid var(--color-primary);
}

.file-item__index {
  font-size: 11px;
  color: var(--color-text-secondary);
  font-family: 'SF Mono', monospace;
  min-width: 20px;
}

.file-item__name {
  flex: 1;
  font-size: 13px;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-item__doc-index {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--color-text-secondary);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 1px 5px;
}

.file-item__status {
  flex-shrink: 0;
}

.preview-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8f9fa;
  min-height: 400px;
  overflow: hidden;
}

.preview-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-fullscreen-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 10;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.preview-image {
  width: 100%;
  height: 100%;
  cursor: pointer;
}

.preview-image :deep(.el-image__inner) {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.preview-pdf {
  width: 100%;
  height: 100%;
  border: none;
}

.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.results-panel {
  flex: 1;
  min-width: 0;
}

.result-header {
  margin-bottom: 4px;
}

.result-title-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.result-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
}

.result-job-id {
  font-size: 13px;
  color: var(--color-text-secondary);
  font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
  background: var(--color-surface);
  padding: 2px 10px;
  border-radius: 4px;
  border: 1px solid var(--color-border);
}

.result-search {
  margin-top: 12px;
}

.search-input {
  max-width: 320px;
}

.result-alert {
  margin: 0;
}

.batch-panel {
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 14px 16px;
}

.batch-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.batch-panel__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.batch-panel__meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.batch-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(138px, 1fr));
  gap: 8px;
  max-height: 180px;
  overflow-y: auto;
}

.batch-item {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 8px;
  align-items: center;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
}

.batch-item--processing {
  border-color: var(--color-primary);
}

.batch-item--completed {
  border-color: var(--color-success);
}

.batch-item--failed,
.batch-item--partial_failed,
.batch-item--timeout_partial {
  border-color: var(--color-danger);
}

.batch-item__index {
  font-family: 'SF Mono', monospace;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.batch-item__status {
  font-size: 12px;
  color: var(--color-text);
}

.batch-item__progress {
  grid-column: 1 / -1;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.live-panel {
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px;
}

.live-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.live-panel__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.live-panel__meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.live-panel__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.live-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.8fr);
  gap: 14px;
}

.live-column {
  min-width: 0;
}

.live-column__title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}

.live-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 260px;
  overflow-y: auto;
}

.live-row {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 9px 10px;
  background: var(--color-surface);
}

.live-row--failed {
  border-color: var(--color-danger-border);
  background: var(--color-danger-bg);
}

.live-row__main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.live-row__file {
  min-width: 0;
  flex: 1;
  color: var(--color-text);
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.live-row__fields {
  display: grid;
  grid-template-columns: 120px 100px repeat(2, minmax(120px, 1fr));
  gap: 8px;
  margin-top: 7px;
  color: var(--color-text-secondary);
  font-size: 12px;
}

.live-row__fields span,
.live-row__error {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.live-row__error {
  margin-top: 7px;
  color: var(--color-danger-text);
  font-size: 12px;
}

.live-empty {
  border: 1px dashed var(--color-border);
  border-radius: 6px;
  padding: 20px 12px;
  color: var(--color-text-secondary);
  font-size: 13px;
  text-align: center;
  background: var(--color-surface);
}

.result-tabs {
  margin-top: 0;
}

.type-tabs > .el-tabs__header {
  margin-bottom: 0;
}

.view-tabs {
  margin-top: 12px;
}

.result-waiting {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--color-text-secondary);
  font-size: 15px;
}

.result-waiting__copy {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}

.result-waiting__title {
  color: var(--color-text-secondary);
}

.result-waiting__meta {
  font-size: 13px;
  color: var(--color-text);
}

/* ---- JSON toolbar ---- */
.json-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.json-summary {
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* ---- JSON result cards ---- */
.json-card {
  background: var(--color-surface-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 16px 20px;
  margin-bottom: 14px;
}

.json-card:last-of-type {
  margin-bottom: 20px;
}

.json-card.is-failed {
  border-color: var(--color-danger-border);
  background: var(--color-danger-bg);
}

.json-failure-reason {
  margin-bottom: 14px;
  border-radius: var(--radius-md);
}

.ocr-error-text {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: var(--color-danger-bg);
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-md);
  color: var(--color-danger-text);
  font-size: 13px;
  line-height: 1.5;
}

.ocr-error-text .el-icon {
  flex-shrink: 0;
  margin-top: 1px;
  font-size: 16px;
}

.json-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border);
}

.json-card-filename {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.json-card-index {
  font-size: 12px;
  color: var(--color-text-secondary);
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.json-card-badges {
  display: flex;
  gap: 6px;
  align-items: center;
}

/* ---- JSON sections ---- */
.json-section {
  margin-bottom: 14px;
}

.json-section:last-child {
  margin-bottom: 0;
}

.json-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

/* ---- OCR line tags ---- */
.ocr-line-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ocr-line-tag {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
}

/* ---- Structured data fields ---- */
.struct-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}

.struct-field {
  display: flex;
  align-items: baseline;
  gap: 4px;
  padding: 6px 10px;
  border-radius: 4px;
  background: var(--color-surface);
  font-size: 13px;
  min-width: 0;
}

.struct-field.is-low-confidence {
  background: var(--color-danger-bg);
  border: 1px solid var(--color-danger-border);
}

.struct-label {
  font-weight: 500;
  color: var(--color-primary);
  flex-shrink: 0;
  white-space: nowrap;
}

.struct-sep {
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.struct-value {
  color: var(--color-text);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.is-low-confidence .struct-value {
  color: var(--color-danger-text);
  font-weight: 600;
}

.struct-confidence {
  font-size: 11px;
  color: var(--color-text-secondary);
  flex-shrink: 0;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

/* ---- Empty state ---- */
.json-empty {
  font-size: 12px;
  color: var(--color-text-secondary);
  font-style: italic;
}

/* ---- Raw JSON section ---- */
.json-raw-section {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--color-border);
}

/* ---- JSON syntax-highlighted viewer ---- */
.json-viewer {
  background: #1e1e2e;
  border-radius: var(--radius-md);
  padding: 20px 24px;
  margin: 0;
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.7;
  overflow-x: auto;
  max-height: 560px;
  overflow-y: auto;
  color: #cdd6f4;
  border: 1px solid var(--color-border);
}

.json-viewer code {
  font-family: inherit;
  font-size: inherit;
}

.json-viewer :deep(.json-key) {
  color: #89b4fa;
}

.json-viewer :deep(.json-string) {
  color: #a6e3a1;
}

.json-viewer :deep(.json-number) {
  color: #fab387;
}

.json-viewer :deep(.json-boolean) {
  color: #fab387;
}

.json-viewer :deep(.json-null) {
  color: #6c7086;
}

/* ---- Fullscreen preview overlay ---- */
.fullscreen-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
}

.fullscreen-viewer {
  width: 95vw;
  height: 95vh;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.fullscreen-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
}

.fullscreen-filename {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 12px;
}

.fullscreen-close-btn {
  font-size: 20px;
  color: #666;
  padding: 4px;
}

.fullscreen-close-btn:hover {
  color: #333;
}

.fullscreen-body {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
  overflow: hidden;
}

.fullscreen-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.fullscreen-image :deep(.el-image__inner) {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.fullscreen-pdf {
  width: 100%;
  height: 100%;
  border: none;
}

@media (max-width: 900px) {
  .result-split,
  .live-columns {
    grid-template-columns: 1fr;
    display: grid;
  }

  .preview-panel {
    width: 100%;
  }

  .live-panel__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .live-panel__actions {
    justify-content: flex-start;
  }

  .live-row__fields {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
