<template>
  <div class="upload-page">
    <div class="page-hero">
      <h1 class="hero-title">智能票据识别</h1>
      <p class="hero-desc">上传发票、收据或银行回单，AI 自动提取结构化信息</p>
    </div>

    <div class="upload-content">
      <FileDropZone v-model="files" />

      <div v-if="files.length" class="preflight-panel">
        <div class="preflight-item">
          <span class="preflight-label">文件数</span>
          <span class="preflight-value">{{ files.length.toLocaleString() }}</span>
        </div>
        <div class="preflight-item">
          <span class="preflight-label">预计批次</span>
          <span class="preflight-value">{{ estimatedBatches }}</span>
        </div>
        <div class="preflight-item">
          <span class="preflight-label">总大小</span>
          <span class="preflight-value">{{ formatSize(totalSize) }}</span>
        </div>
        <div class="preflight-warning" v-if="preflightWarning">
          {{ preflightWarning }}
        </div>
        <div class="preflight-notice" v-else-if="preflightNotice">
          {{ preflightNotice }}
        </div>
      </div>

      <el-alert
        v-if="uploadError"
        :title="uploadError"
        type="error"
        :closable="false"
        show-icon
        class="upload-alert"
      />

      <div v-if="uploading" class="upload-progress">
        <el-progress :percentage="uploadPercent" :stroke-width="8" :show-text="false" />
        <span class="upload-progress-text">{{ uploadStatusText }}</span>
      </div>

      <div class="upload-actions">
        <el-button
          type="primary"
          size="large"
          :icon="UploadIcon"
          :loading="uploading"
          :disabled="!files.length || Boolean(preflightWarning)"
          @click="handleUpload"
        >
          {{ uploading ? '上传中...' : '上传并识别' }}
        </el-button>
        <span class="action-hint" v-if="!files.length">请先选择文件</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Upload as UploadIcon } from '@element-plus/icons-vue'
import FileDropZone from '../components/FileDropZone.vue'
import {
  completeUploadSession,
  createUploadSession,
  getUploadSession,
  startProcess,
  uploadFiles,
  uploadSessionChunk,
} from '../api'

const router = useRouter()

const files = ref([])
const uploading = ref(false)
const uploadError = ref('')
const uploadPercent = ref(0)
const MAX_FILES = 20000
const ZIP_RECOMMEND_FILE_COUNT = 1000
const CHILD_BATCH_SIZE = 300
const MAX_SINGLE_FILE_SIZE = 200 * 1024 * 1024
const RESUMABLE_CHUNK_SIZE = 300
const CHUNK_RETRY_LIMIT = 2
const resumableUploadId = ref('')
const uploadStatusText = ref('')

const totalSize = computed(() => files.value.reduce((sum, file) => sum + (file.size || 0), 0))
const fileSelectionSignature = computed(() => files.value.map((file) => `${file.name}:${file.size}`).join('|'))
const estimatedBatches = computed(() => Math.max(1, Math.ceil(files.value.length / CHILD_BATCH_SIZE)))
const oversizedCount = computed(() => files.value.filter((file) => (file.size || 0) > MAX_SINGLE_FILE_SIZE).length)
const preflightWarning = computed(() => {
  if (files.value.length > MAX_FILES) return `单次最多 ${MAX_FILES.toLocaleString()} 个文件，请分多次上传`
  if (oversizedCount.value) return `${oversizedCount.value} 个文件超过 200MB，请移除后再上传`
  return ''
})
const preflightNotice = computed(() => {
  if (files.value.length > ZIP_RECOMMEND_FILE_COUNT) {
    return `已超过 ${ZIP_RECOMMEND_FILE_COUNT.toLocaleString()} 个文件。建议先打包成 ZIP 再上传；如继续上传散文件，系统会自动使用分片断点续传。`
  }
  return ''
})

watch(fileSelectionSignature, () => {
  if (!uploading.value) {
    resumableUploadId.value = ''
  }
})

async function handleUpload() {
  if (!files.value.length) return

  uploading.value = true
  uploadError.value = ''
  uploadPercent.value = 0
  uploadStatusText.value = '准备上传...'

  try {
    const uploadRes = files.value.length > ZIP_RECOMMEND_FILE_COUNT
      ? await uploadResumable()
      : await uploadClassic()
    const { job_id } = uploadRes.data

    uploadStatusText.value = '上传完成，正在创建识别任务...'
    await startProcess(job_id)

    router.push({ name: 'Result', params: { jobId: job_id } })
  } catch (err) {
    const msg = err.response?.data?.detail || err.message || '上传失败，请重试'
    uploadError.value = msg
  } finally {
    uploading.value = false
    uploadPercent.value = 0
    uploadStatusText.value = ''
  }
}

async function uploadClassic() {
  const formData = new FormData()
  files.value.forEach((f) => formData.append('files', f))
  uploadStatusText.value = '上传中 0%'
  return uploadFiles(formData, (pct) => {
    uploadPercent.value = pct
    uploadStatusText.value = `上传中 ${pct}%`
  })
}

async function uploadResumable() {
  const chunks = chunkFiles(files.value, RESUMABLE_CHUNK_SIZE)
  let session
  if (resumableUploadId.value) {
    session = (await getUploadSession(resumableUploadId.value)).data
  } else {
    session = (await createUploadSession({
      total_files: files.value.length,
      total_size: totalSize.value,
      total_chunks: chunks.length,
      chunk_size: RESUMABLE_CHUNK_SIZE,
    })).data
    resumableUploadId.value = session.upload_id
  }

  const completed = new Set(session.completed_chunks || [])
  for (let index = 0; index < chunks.length; index++) {
    if (completed.has(index)) {
      updateResumableProgress(index, chunks.length, 100)
      continue
    }
    await uploadChunkWithRetry(session.upload_id, index, chunks[index], chunks.length)
    completed.add(index)
  }
  uploadPercent.value = 100
  uploadStatusText.value = '分片上传完成，正在合并...'
  const response = await completeUploadSession(session.upload_id)
  resumableUploadId.value = ''
  return response
}

async function uploadChunkWithRetry(uploadId, chunkIndex, chunkFilesList, totalChunks) {
  let lastError = null
  for (let attempt = 1; attempt <= CHUNK_RETRY_LIMIT + 1; attempt++) {
    try {
      const formData = new FormData()
      chunkFilesList.forEach((file) => formData.append('files', file))
      await uploadSessionChunk(uploadId, chunkIndex, formData, (pct) => {
        updateResumableProgress(chunkIndex, totalChunks, pct)
      })
      updateResumableProgress(chunkIndex, totalChunks, 100)
      return
    } catch (err) {
      lastError = err
      if (attempt <= CHUNK_RETRY_LIMIT) {
        uploadStatusText.value = `第 ${chunkIndex + 1}/${totalChunks} 片上传失败，正在重试 ${attempt}/${CHUNK_RETRY_LIMIT}...`
        await sleep(800 * attempt)
      }
    }
  }
  throw lastError
}

function updateResumableProgress(doneChunkBase, totalChunks, chunkPercent) {
  const currentPercent = ((doneChunkBase + (chunkPercent / 100)) / totalChunks) * 100
  uploadPercent.value = Math.min(99, Math.round(currentPercent))
  const displayChunk = Math.min(totalChunks, doneChunkBase + 1)
  uploadStatusText.value = `分片上传中 ${displayChunk}/${totalChunks}，总进度 ${uploadPercent.value}%`
}

function chunkFiles(sourceFiles, size) {
  const chunks = []
  for (let index = 0; index < sourceFiles.length; index += size) {
    chunks.push(sourceFiles.slice(index, index + size))
  }
  return chunks
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}
</script>

<style scoped>
.upload-page {
  max-width: 780px;
  margin: 0 auto;
}

.page-hero {
  text-align: center;
  margin-bottom: 32px;
}

.hero-title {
  font-size: 28px;
  font-weight: 800;
  color: var(--color-text);
  letter-spacing: -0.02em;
  margin-bottom: 8px;
}

.hero-desc {
  font-size: 15px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.upload-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.upload-alert {
  margin: 0;
}

.upload-progress {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.upload-progress-text {
  font-size: 12px;
  color: var(--color-text-secondary);
  text-align: right;
}

.preflight-panel {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface-card);
}

.preflight-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.preflight-label {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.preflight-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
}

.preflight-warning {
  grid-column: 1 / -1;
  font-size: 13px;
  color: var(--color-danger-text);
  background: var(--color-danger-bg);
  border-radius: 6px;
  padding: 8px 10px;
}

.preflight-notice {
  grid-column: 1 / -1;
  font-size: 13px;
  color: var(--color-warning-text);
  background: var(--color-warning-bg);
  border-radius: 6px;
  padding: 8px 10px;
}

.upload-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.action-hint {
  font-size: 13px;
  color: var(--color-text-secondary);
}
</style>
