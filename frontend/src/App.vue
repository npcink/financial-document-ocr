<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="header-brand" @click="$router.push('/')">
        <span class="brand-icon">📄</span>
        <span class="brand-text">发票智能识别系统</span>
      </div>
      <nav class="header-nav">
        <router-link to="/" class="nav-link" active-class="nav-link--active">
          <el-icon><Upload /></el-icon>
          <span>上传</span>
        </router-link>
        <router-link to="/ocr" class="nav-link" active-class="nav-link--active">
          <el-icon><View /></el-icon>
          <span>OCR</span>
        </router-link>
        <router-link to="/tasks" class="nav-link" active-class="nav-link--active">
          <el-icon><List /></el-icon>
          <span>任务</span>
        </router-link>
      </nav>
      <div class="header-status">
        <el-tag :type="healthStatus.type" size="small" effect="dark" round>
          {{ healthStatus.label }}
        </el-tag>
        <el-tooltip :content="sessionId" placement="bottom" raw-content>
          <el-tag size="small" effect="plain" class="session-tag">
            <el-icon><Monitor /></el-icon>
            <span>会话 {{ sessionId.slice(0, 6) }}</span>
          </el-tag>
        </el-tooltip>
      </div>
    </header>
    <div class="app-banner">
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>
          使用问题私聊学义 | 当前使用云端模型，请勿导入机密文件
        </template>
      </el-alert>
    </div>
    <main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- Full-page drag overlay -->
    <transition name="overlay-fade">
      <div v-if="isDragging" class="drag-overlay">
        <div class="drag-overlay__content">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          <p>释放以上传文件</p>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, provide } from 'vue'
import { Upload, List, View, Monitor } from '@element-plus/icons-vue'
import { healthCheck } from './api'

const healthStatus = ref({ type: 'info', label: '检测中...' })
const sessionId = ref(localStorage.getItem('session_id') || '------')
const isDragging = ref(false)

// Provide a function for FileDropZone to register a callback
const dropCallbacks = ref([])
function onFilesDropped(files) {
  dropCallbacks.value.forEach(cb => cb(files))
}
provide('registerDropCallback', (cb) => {
  dropCallbacks.value.push(cb)
})

let healthTimer = null
let dragCounter = 0

function handleWindowDragOver(e) {
  e.preventDefault()
  e.dataTransfer.dropEffect = 'copy'
  dragCounter++
  if (dragCounter === 1) {
    isDragging.value = true
  }
}

function handleWindowDragLeave(e) {
  // Only hide overlay when leaving the window entirely
  if (e.clientX <= 0 || e.clientY <= 0 ||
      e.clientX >= window.innerWidth || e.clientY >= window.innerHeight) {
    dragCounter = 0
    isDragging.value = false
  }
}

function handleWindowDrop(e) {
  e.preventDefault()
  dragCounter = 0
  isDragging.value = false

  const items = e.dataTransfer.items
  if (items) {
    const droppedFiles = []
    const entries = []
    for (let i = 0; i < items.length; i++) {
      const item = items[i]
      const entry = item.webkitGetAsEntry?.()
      if (entry) {
        entries.push(entry)
      } else if (item.kind === 'file') {
        const file = item.getAsFile()
        if (file) droppedFiles.push(file)
      }
    }

    if (entries.length > 0) {
      readEntries(entries).then(folderFiles => {
        const allFiles = [...folderFiles.flat(), ...droppedFiles]
        if (allFiles.length) onFilesDropped(allFiles)
      })
    } else if (droppedFiles.length) {
      onFilesDropped(droppedFiles)
    }
    return
  }

  // Fallback
  const files = Array.from(e.dataTransfer.files)
  if (files.length) onFilesDropped(files)
}

function readEntries(entries) {
  return Promise.all(entries.map(readEntry)).then(results => results.flat())
}

function readEntry(entry) {
  return new Promise((resolve) => {
    if (entry.isFile) {
      entry.file((file) => resolve([file]))
    } else if (entry.isDirectory) {
      const reader = entry.createReader()
      const allEntries = []
      const readBatch = () => {
        reader.readEntries((batch) => {
          if (batch.length === 0) {
            Promise.all(allEntries.map(readEntry)).then((results) => {
              resolve(results.flat())
            })
          } else {
            allEntries.push(...batch)
            readBatch()
          }
        })
      }
      readBatch()
    } else {
      resolve([])
    }
  })
}

async function checkHealth() {
  try {
    const res = await healthCheck()
    const { status } = res.data
    if (status === 'healthy') {
      healthStatus.value = { type: 'success', label: '服务正常' }
    } else if (status === 'degraded') {
      healthStatus.value = { type: 'warning', label: '部分可用' }
    } else {
      healthStatus.value = { type: 'danger', label: '服务异常' }
    }
  } catch {
    healthStatus.value = { type: 'danger', label: '连接失败' }
  }
}

onMounted(() => {
  checkHealth()
  healthTimer = setInterval(checkHealth, 30000)

  // Use capture phase to intercept drag events before any child element
  window.addEventListener('dragover', handleWindowDragOver, { capture: true, passive: false })
  window.addEventListener('dragleave', handleWindowDragLeave, { capture: true })
  window.addEventListener('drop', handleWindowDrop, { capture: true })
})

onUnmounted(() => {
  clearInterval(healthTimer)
  window.removeEventListener('dragover', handleWindowDragOver, { capture: true })
  window.removeEventListener('dragleave', handleWindowDragLeave, { capture: true })
  window.removeEventListener('drop', handleWindowDrop, { capture: true })
})
</script>

<style>
:root {
  --color-primary: #4f46e5;
  --color-primary-light: #818cf8;
  --color-primary-dark: #3730a3;
  --color-surface: #f8fafc;
  --color-surface-card: #ffffff;
  --color-text: #1e293b;
  --color-text-secondary: #64748b;
  --color-border: #e2e8f0;
  --color-danger-bg: #fef2f2;
  --color-danger-text: #991b1b;
  --color-danger-border: #fecaca;
  --color-success: #059669;
  --color-warning: #d97706;
  --radius-md: 8px;
  --radius-lg: 12px;
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.04);
}

*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
    'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial,
    sans-serif;
  font-size: 14px;
  color: var(--color-text);
  background: var(--color-surface);
  -webkit-font-smoothing: antialiased;
}

#app {
  height: 100%;
}

.el-button--primary {
  --el-button-bg-color: var(--color-primary);
  --el-button-border-color: var(--color-primary);
  --el-button-hover-bg-color: var(--color-primary-light);
  --el-button-hover-border-color: var(--color-primary-light);
}

.el-tag--primary {
  --el-tag-bg-color: rgba(79, 70, 229, 0.1);
  --el-tag-border-color: rgba(79, 70, 229, 0.2);
  --el-tag-text-color: var(--color-primary);
}

.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity 0.2s ease;
}

.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
}

.drag-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(79, 70, 229, 0.08);
  backdrop-filter: blur(4px);
  border: 3px dashed var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.drag-overlay__content {
  text-align: center;
  color: var(--color-primary);
  pointer-events: none;
}

.drag-overlay__content svg {
  opacity: 0.6;
  margin-bottom: 12px;
}

.drag-overlay__content p {
  font-size: 18px;
  font-weight: 600;
}
</style>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.app-header {
  display: flex;
  align-items: center;
  height: 56px;
  padding: 0 24px;
  background: #ffffff;
  border-bottom: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
  z-index: 100;
  gap: 32px;
}

.app-banner {
  padding: 0 24px;
  padding-top: 16px;
}

.app-banner .el-alert {
  border-radius: var(--radius-md);
  font-weight: 500;
}

.app-banner .el-alert__title {
  font-size: 14px;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}

.brand-icon {
  font-size: 22px;
  line-height: 1;
}

.brand-text {
  font-size: 17px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.header-nav {
  display: flex;
  gap: 4px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-secondary);
  text-decoration: none;
  transition: all 0.15s ease;
}

.nav-link:hover {
  color: var(--color-primary);
  background: rgba(79, 70, 229, 0.06);
}

.nav-link--active {
  color: var(--color-primary);
  background: rgba(79, 70, 229, 0.08);
}

.header-status {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-tag {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: 11px;
  cursor: default;
}

.app-main {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
</style>
