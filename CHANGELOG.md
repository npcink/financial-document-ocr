# 变更日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/) 的结构。

## [Unreleased]

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
