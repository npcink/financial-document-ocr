# 变更日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/) 的结构。

## [Unreleased]

### Changed

- 使用宽松许可的 `pypdfium2`/PDFium 替换 AGPL/商业双许可的 PyMuPDF，保持
  150 DPI、多页 PDF 和最多处理 50 页的 OCR 行为。

### Added

- 加入 `GPL-3.0-only` 项目许可证和 PDF 渲染依赖的第三方许可说明。

### Security

- Docker 构建上下文排除密钥、运行数据、业务文档和备份文件。
- 运行日志使用进程内不可逆标签代替原始文件名和任务标识，并移除异常消息与
  结构化财务字段名称。
- 上传文件名与 HTTP 任务/上传标识在访问文件系统前进行格式校验，所有路径经真实路径
  解析后限制在受信任的数据目录内。

## [3.0.0] - 2026-07-15

### Added

- Vue 3、FastAPI、SQLite、Docker Compose 一体化运行方式。
- 图片、PDF、ZIP 和常见办公文档批量上传。
- 云端模型与本地 Ollama 双运行模式。
- 任务队列、断点续传、结果审阅、重试和 Excel/CSV 导出。
- 定时数据清理、源码备份校验和依赖更新自动化。

### Security

- `.env`、数据库、上传件、导出件和构建产物不进入 Git 或源码备份。
- 文档明确说明会话标识、云端数据处理和受信任网络边界。
