# 系统架构

## 目标

本服务把财务图片和文档批量转换为可审阅、可重试、可导出的结构化结果。前端和 API 由同一容器提供，运行数据位于独立数据目录。

## 组件

| 组件 | 位置 | 职责 |
|---|---|---|
| Vue 前端 | `frontend/src` | 上传、任务列表、进度、结果审阅和导出 |
| FastAPI 入口 | `backend/app/main.py` | 路由、静态文件、启动恢复和定时清理 |
| 上传路由 | `backend/app/routers/upload.py` | 上传、分批和断点续传 |
| 任务路由 | `backend/app/routers/process.py` | 启动、查询、重试和结果分页 |
| 处理流水线 | `backend/app/services/pipeline.py` | OCR、分类、提取、归一化和状态更新 |
| 驱动层 | `backend/app/drivers` | 云端模型与本地 Ollama 适配 |
| 导出层 | `backend/app/services/excel.py` | Excel、CSV 和多任务合并导出 |
| 数据层 | `backend/app/db.py` | SQLite、WAL、连接池、任务隔离和过期清理 |

## 处理流程

```text
浏览器生成 X-Session-ID
  -> 上传文件并创建任务
  -> 大任务拆分为子任务
  -> 队列和信号量控制并发
  -> OCR 提取文本和版面信息
  -> 分类并提取结构化字段
  -> 归一化和置信度校验
  -> SQLite 持久化
  -> 前端通过查询或 SSE 获取结果
  -> Excel/CSV 导出
```

## 数据布局

```text
/app/data/jobs.db          任务、结果和缓存
/app/data/uploads/         上传和处理中间文件
/app/data/exports/         临时导出文件
```

宿主机通过 `HOST_DATA_DIR` 映射整个目录。SQLite 使用 WAL 模式；在线备份必须使用 SQLite `.backup`，不能直接复制写入中的数据库。

## AI 模式

- `AI_MODE=cloud`：文档图像和 OCR 文本会发送给配置的云端服务。
- `AI_MODE=local`：请求发送给配置的 Ollama 地址；是否离线由部署网络决定。

两种驱动保持相同的业务接口，避免切换模式时产生分支语义。

## 安全边界

- `X-Session-ID` 是任务隔离标识，不是身份认证。
- 默认 Compose 端口映射不应直接暴露到不受信任网络。
- 公网部署需要独立的 HTTPS、认证、授权、限流和访问日志层。
- `.env`、数据库、上传件、导出件和模型输出不得进入 Git 或普通源码包。
- `CLEANUP_HOURS` 只提供运行时保留期清理，不能替代加密、访问控制或备份保留策略。
