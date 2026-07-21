import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

function getSessionId() {
  let sid = localStorage.getItem('session_id')
  if (!sid) {
    sid = createSessionId()
    localStorage.setItem('session_id', sid)
  }
  return sid
}

function createSessionId() {
  const cryptoApi = globalThis.crypto

  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return cryptoApi.randomUUID()
  }

  if (cryptoApi && typeof cryptoApi.getRandomValues === 'function') {
    const bytes = new Uint8Array(16)
    cryptoApi.getRandomValues(bytes)
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }

  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

api.interceptors.request.use((config) => {
  config.headers['X-Session-ID'] = getSessionId()
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('session_id')
      window.location.reload()
    }
    return Promise.reject(err)
  }
)

export function healthCheck() {
  return api.get('/health/')
}

export function uploadFiles(formData, onProgress) {
  return api.post('/upload/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 1800000,
    onUploadProgress: onProgress ? (e) => onProgress(e.total ? Math.round((e.loaded * 100) / e.total) : 0) : undefined,
  })
}

export function createUploadSession(payload) {
  return api.post('/upload/session', payload)
}

export function getUploadSession(uploadId) {
  return api.get(`/upload/session/${uploadId}`)
}

export function uploadSessionChunk(uploadId, chunkIndex, formData, onProgress) {
  return api.post(`/upload/session/${uploadId}/chunks/${chunkIndex}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000,
    onUploadProgress: onProgress ? (e) => onProgress(e.total ? Math.round((e.loaded * 100) / e.total) : 0) : undefined,
  })
}

export function completeUploadSession(uploadId) {
  return api.post(`/upload/session/${uploadId}/complete`, null, {
    timeout: 600000,
  })
}

export function listJobs({ limit = 20, offset = 0 } = {}) {
  return api.get('/process/', { params: { limit, offset } })
}

export function startProcess(jobId, options = {}) {
  return api.post(`/process/${jobId}`, {
    template_type: options.template_type || 'general',
    requirement: options.requirement || '',
  })
}

export function deleteJob(jobId) {
  return api.delete(`/process/${jobId}`)
}

export function getJobStatus(jobId) {
  return api.get(`/process/${jobId}`)
}

export function getJobBatches(jobId) {
  return api.get(`/process/${jobId}/batches`)
}

export function getJobResults(jobId) {
  return api.get(`/process/${jobId}/results`)
}

export function getJobResultsSummary(jobId, { limit = 500, offset = 0 } = {}) {
  return api.get(`/process/${jobId}/results/summary`, { params: { limit, offset } })
}

export function getJobRecentResults(jobId, { limit = 50, status = '' } = {}) {
  return api.get(`/process/${jobId}/results/recent`, { params: { limit, status } })
}

export function getJobResultDetail(jobId, resultId) {
  return api.get(`/process/${jobId}/results/${resultId}`)
}

export function ocrRecognize(formData) {
  return api.post('/ocr/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000,
  })
}

export function retryAll(jobId) {
  return api.post(`/process/${jobId}/retry-all`)
}

export function retryUnfinished(jobId) {
  return api.post(`/process/${jobId}/retry-unfinished`)
}

export function retrySingle(jobId, resultId) {
  return api.post(`/process/${jobId}/retry/${resultId}`)
}

export function downloadExcel(jobId, columns = '', format = 'xlsx', includePartial = false, detail = 'standard') {
  return api.get(`/export/${jobId}`, {
    params: { columns, format, include_partial: includePartial, detail },
    responseType: 'blob',
  })
}

export function downloadMergedStandardExport(jobIds, format = 'xlsx', includePartial = false, detail = 'standard') {
  return api.post('/export/merge', {
    job_ids: jobIds,
    format,
    include_partial: includePartial,
    detail,
  }, {
    responseType: 'blob',
    timeout: 600000,
  })
}

export function createJobStream(jobId, sessionId) {
  const url = `${api.defaults.baseURL}/process/${jobId}/stream`
  const es = new EventSource(`${url}?session_id=${sessionId}`)
  return es
}
