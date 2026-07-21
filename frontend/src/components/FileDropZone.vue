<template>
  <div
    class="drop-zone"
    :class="{ 'drop-zone--active': isDragover, 'drop-zone--has-files': files.length > 0 }"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent="onDragOver"
    @dragleave.prevent="onDragLeave"
    @drop.prevent="onDrop"
  >
    <input
      ref="fileInput"
      type="file"
      multiple
      :accept="accept"
      class="drop-zone__input"
      @change="onFileChange"
    />
    <input
      ref="folderInput"
      type="file"
      multiple
      webkitdirectory
      mozdirectory
      directory
      class="drop-zone__input"
      @change="onFolderChange"
    />

    <div class="drop-zone__content">
      <div class="drop-zone__icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
      </div>
      <p class="drop-zone__title">拖拽文件或文件夹到此处上传</p>
      <p class="drop-zone__hint">
        支持 ZIP/图片/PDF/Word/Excel/HTML/XML &nbsp;·&nbsp; 超过 1,000 张建议打包 ZIP 上传，单次最多 20,000 个文件
      </p>
      <div class="drop-zone__actions">
        <el-button
          type="primary"
          :icon="UploadIcon"
          class="drop-zone__btn"
          @click.stop="fileInput?.click()"
        >
          选择文件
        </el-button>
        <el-button
          type="default"
          :icon="FolderIcon"
          class="drop-zone__btn"
          @click.stop="folderInput?.click()"
        >
          选择文件夹
        </el-button>
      </div>
    </div>

    <transition name="file-list-fade">
      <div v-if="files.length > 0" class="drop-zone__files">
        <div class="files-header">
          <span>已选择 {{ files.length }} 个文件</span>
          <el-button text type="danger" size="small" @click="clearFiles">清空</el-button>
        </div>
        <ul class="files-list">
          <li v-for="(f, i) in displayedFiles" :key="i" class="file-item">
            <span class="file-item__name">{{ f.name }}</span>
            <span class="file-item__size">{{ formatSize(f.size) }}</span>
            <el-button text type="danger" size="small" class="file-item__remove" @click.stop="removeFile(i)">✕</el-button>
          </li>
          <li v-if="hiddenFileCount > 0" class="file-item file-item--more">
            还有 {{ hiddenFileCount }} 个文件未展开显示
          </li>
        </ul>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, inject, onMounted } from 'vue'
import { Upload as UploadIcon, Folder as FolderIcon } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  accept: { type: String, default: '.zip,.png,.jpg,.jpeg,.bmp,.tiff,.tif,.webp,.pdf,.docx,.xlsx,.xls,.html,.htm,.xml' },
})

const emit = defineEmits(['update:modelValue'])

const fileInput = ref(null)
const folderInput = ref(null)
const isDragover = ref(false)

const files = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})
const MAX_VISIBLE_FILES = 200
const displayedFiles = computed(() => files.value.slice(0, MAX_VISIBLE_FILES))
const hiddenFileCount = computed(() => Math.max(0, files.value.length - MAX_VISIBLE_FILES))

// Register with app-level drop handler
const registerDropCallback = inject('registerDropCallback', null)
function handleAppDrop(appFiles) {
  addFiles(appFiles)
}
onMounted(() => {
  registerDropCallback?.(handleAppDrop)
})

const SUPPORTED_EXT = new Set(['.zip', '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp', '.pdf', '.docx', '.xlsx', '.xls', '.html', '.htm', '.xml'])

function isSupported(file) {
  if (!file || !file.name) return false
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  return SUPPORTED_EXT.has(ext)
}

function deduplicateFiles(existing, newFiles) {
  const existingKeys = new Set(existing.map(f => `${f.name}|${f.size}`))
  return newFiles.filter(f => !existingKeys.has(`${f.name}|${f.size}`))
}

function addFiles(newFiles) {
  const filtered = newFiles.filter(isSupported)
  if (!filtered.length) return
  const unique = deduplicateFiles(files.value, filtered)
  if (unique.length) {
    files.value = [...files.value, ...unique]
  }
}

let dragCounter = 0

function onDragEnter() {
  dragCounter++
  isDragover.value = true
}

function onDragOver(e) {
  e.dataTransfer.dropEffect = 'copy'
}

function onDragLeave() {
  dragCounter--
  if (dragCounter <= 0) {
    isDragover.value = false
    dragCounter = 0
  }
}

async function onDrop(e) {
  dragCounter = 0
  isDragover.value = false

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
      const folderFiles = await readEntries(entries)
      addFiles(folderFiles)
    } else if (droppedFiles.length) {
      addFiles(droppedFiles)
    }
    return
  }

  // Fallback for browsers that don't support dataTransfer.items
  const droppedFiles = Array.from(e.dataTransfer.files)
  if (droppedFiles.length) addFiles(droppedFiles)
}

function readEntries(entries) {
  return Promise.all(entries.map(readEntry))
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

function onFileChange(e) {
  const selected = Array.from(e.target.files)
  if (selected.length) addFiles(selected)
  e.target.value = ''
}

function onFolderChange(e) {
  const selected = Array.from(e.target.files)
  if (selected.length) addFiles(selected)
  e.target.value = ''
}

function clearFiles() {
  files.value = []
  if (fileInput.value) fileInput.value.value = ''
  if (folderInput.value) folderInput.value.value = ''
}

function removeFile(index) {
  const newFiles = [...files.value]
  newFiles.splice(index, 1)
  files.value = newFiles
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.drop-zone {
  position: relative;
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-lg);
  padding: 48px 24px;
  text-align: center;
  transition: all 0.2s ease;
  background: var(--color-surface-card);
  cursor: pointer;
}

.drop-zone:hover {
  border-color: var(--color-primary-light);
  background: rgba(79, 70, 229, 0.02);
}

.drop-zone--active {
  border-color: var(--color-primary);
  background: rgba(79, 70, 229, 0.04);
  box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.1);
}

.drop-zone--has-files {
  padding: 24px;
}

.drop-zone__input {
  display: none;
}

.drop-zone__icon {
  color: var(--color-primary-light);
  margin-bottom: 16px;
  opacity: 0.8;
}

.drop-zone__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 6px;
}

.drop-zone__hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 20px;
}

.drop-zone__btn {
  margin-top: 4px;
}

.drop-zone__actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 4px;
}

.drop-zone__files {
  margin-top: 20px;
  text-align: left;
}

.files-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.files-list {
  list-style: none;
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  font-size: 13px;
  border-bottom: 1px solid var(--color-border);
}

.file-item:last-child {
  border-bottom: none;
}

.file-item--more {
  justify-content: center;
  color: var(--color-text-secondary);
  background: var(--color-surface);
}

.file-item__name {
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 12px;
}

.file-item__size {
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.file-item__remove {
  flex-shrink: 0;
  margin-left: 8px;
  padding: 0;
  min-width: 20px;
}

.file-list-fade-enter-active {
  transition: all 0.3s ease;
}

.file-list-fade-leave-active {
  transition: all 0.2s ease;
}

.file-list-fade-enter-from,
.file-list-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
