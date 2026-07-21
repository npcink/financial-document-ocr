import { createRouter, createWebHistory } from 'vue-router'
import UploadView from '../views/UploadView.vue'
import TaskView from '../views/TaskView.vue'
import ResultView from '../views/ResultView.vue'
import OcrView from '../views/OcrView.vue'

const routes = [
  {
    path: '/',
    name: 'Upload',
    component: UploadView,
    meta: { title: '上传文件' },
  },
  {
    path: '/ocr',
    name: 'Ocr',
    component: OcrView,
    meta: { title: 'OCR 识别' },
  },
  {
    path: '/tasks',
    name: 'Tasks',
    component: TaskView,
    meta: { title: '任务列表' },
  },
  {
    path: '/result/:jobId',
    name: 'Result',
    component: ResultView,
    props: true,
    meta: { title: '识别结果' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta.title) {
    document.title = `${to.meta.title} - 发票智能识别系统`
  }
})

export default router
