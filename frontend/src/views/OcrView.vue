<template>
  <div class="ocr-page">
    <div class="page-hero">
      <h1 class="hero-title">纯 OCR 识别</h1>
      <p class="hero-desc">上传图片或 PDF，直接提取 OCR 文字结果，跳过 AI 结构化解析</p>
    </div>

    <div class="ocr-content">
      <FileDropZone v-model="files" />

      <el-alert
        v-if="uploadError"
        :title="uploadError"
        type="error"
        :closable="false"
        show-icon
        class="ocr-alert"
      />

      <div class="ocr-actions">
        <el-button
          type="primary"
          size="large"
          :icon="UploadIcon"
          :loading="recognizing"
          :disabled="!files.length"
          @click="handleRecognize"
        >
          {{ recognizing ? '识别中...' : '开始 OCR 识别' }}
        </el-button>
        <span class="action-hint" v-if="!files.length">请先选择文件</span>
        <span class="action-hint" v-else-if="recognizing">正在提取文字，请稍候...</span>
      </div>

      <!-- Results -->
      <template v-if="results.length > 0">
        <el-tabs v-model="activeTab" class="result-tabs">
          <el-tab-pane label="表格视图" name="table">
            <el-table :data="results" stripe class="result-table" max-height="500">
              <el-table-column type="index" label="#" width="50" align="center" />
              <el-table-column prop="filename" label="文件名" min-width="180">
                <template #default="{ row }">
                  <el-tag size="small" type="info" effect="plain">{{ row.filename }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="ocr_text" label="OCR 识别文本" min-width="300">
                <template #default="{ row }">
                  <div class="ocr-text-cell">{{ row.ocr_text || '(无文字)' }}</div>
                </template>
              </el-table-column>
              <el-table-column label="字符数" width="90" align="center">
                <template #default="{ row }">
                  {{ row.word_count ?? 0 }}
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane name="json">
            <template #label>
              <span>JSON 视图</span>
            </template>

            <div class="json-toolbar">
              <span class="json-summary">
                共 {{ results.length }} 条结果
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

            <pre class="json-viewer"><code v-html="highlightedJson"></code></pre>
          </el-tab-pane>
        </el-tabs>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Upload as UploadIcon, CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import FileDropZone from '../components/FileDropZone.vue'
import { ocrRecognize } from '../api'

// ---- state ----
const files = ref([])
const recognizing = ref(false)
const uploadError = ref('')
const results = ref([])
const activeTab = ref('table')
const copied = ref(false)

// ---- JSON highlight ----
const highlightedJson = computed(() => {
  const jsonStr = JSON.stringify(
    { total_files: results.value.length, results: results.value },
    null,
    2
  )
  return syntaxHighlight(jsonStr)
})

function syntaxHighlight(json) {
  // escape HTML entities first
  const escaped = json
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // mark JSON tokens with span classes
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

// ---- actions ----
async function handleRecognize() {
  if (!files.value.length) return

  recognizing.value = true
  uploadError.value = ''
  results.value = []
  activeTab.value = 'table'

  try {
    const formData = new FormData()
    files.value.forEach((f) => formData.append('files', f))

    const res = await ocrRecognize(formData)
    results.value = res.data.results ?? []
  } catch (err) {
    const msg = err.response?.data?.detail || err.message || 'OCR 识别失败，请重试'
    uploadError.value = msg
  } finally {
    recognizing.value = false
  }
}

async function copyJson() {
  try {
    const jsonStr = JSON.stringify(
      { total_files: results.value.length, results: results.value },
      null,
      2
    )
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
</script>

<style scoped>
.ocr-page {
  max-width: 900px;
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

.ocr-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.ocr-alert {
  margin: 0;
}

.ocr-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.action-hint {
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* ---- results ---- */
.result-tabs {
  margin-top: 8px;
}

.result-table {
  border-radius: var(--radius-md);
  overflow: hidden;
}

.ocr-text-cell {
  max-height: 120px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text);
}

/* ---- JSON view ---- */
.json-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding: 0 4px;
}

.json-summary {
  font-size: 13px;
  color: var(--color-text-secondary);
}

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

/* syntax highlight classes */
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
</style>
