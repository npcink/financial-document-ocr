# Financial Document OCR

将图片、PDF、ZIP 和常见办公文档中的发票、收据、银行回单等财务材料转换为结构化结果，并导出为 Excel 或 CSV。系统由 Vue 3 前端和 FastAPI 后端组成，可通过 Docker Compose 运行。

## 安全提示

- `X-Session-ID` 只用于任务隔离，不是用户身份认证。
- 默认服务监听宿主机端口，适合本机或受信任网络使用；面向不受信任网络时必须增加 HTTPS、身份认证、访问控制和限流。
- `AI_MODE=cloud` 会把文档图像和 OCR 文本发送给配置的云端模型服务。处理真实财务材料前，请确认数据处理、留存和合规要求。
- `.env`、SQLite、上传件和导出件都可能包含敏感信息，不得提交到 Git。

详见 [SECURITY.md](SECURITY.md) 和 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 快速开始

要求：Docker Engine 与 Docker Compose v2。

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env；cloud 模式需要配置 SILICONFLOW_API_KEY
chmod 600 backend/.env

docker compose config --quiet
docker compose up -d --build
docker compose ps
```

默认访问地址：<http://localhost:8300/>。

使用其他端口或数据目录：

```bash
HOST_PORT=18000 \
HOST_DATA_DIR=./data-dev \
COMPOSE_PROJECT_NAME=invoice-ocr-dev \
docker compose up -d --build
```

## 运行模式

云端模式：

```dotenv
AI_MODE=cloud
SILICONFLOW_API_KEY=replace_me
OCR_MODEL_CLOUD=deepseek-ai/DeepSeek-OCR
LLM_MODEL_CLOUD=deepseek-ai/DeepSeek-V4-Flash
```

本地模式：

```dotenv
AI_MODE=local
OLLAMA_HOST=http://host.docker.internal:11434
OCR_MODEL_LOCAL=glm-ocr:latest
LLM_MODEL_LOCAL=qwen3.6:27b
```

`AI_MODE=local` 只表示调用配置的 Ollama 地址；是否完全离线取决于实际网络和模型部署。

## 数据流

```text
上传文件
  -> 保存到 data/uploads/{job_id}
  -> OCR
  -> 文档分类与字段提取
  -> 字段归一化和置信度校验
  -> SQLite 保存任务及结果
  -> 前端审阅和重试
  -> Excel/CSV 导出
```

运行数据默认位于 `./data`，不会进入 Docker 镜像或源码备份。

## 主要接口

所有 `/api/*` 请求都需要 `X-Session-ID` 请求头或 `session_id` 查询参数。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/health/` | OCR 与 LLM 可用性 |
| `POST` | `/api/upload/` | 上传文件并创建任务 |
| `POST` | `/api/process/{job_id}` | 启动任务 |
| `GET` | `/api/process/{job_id}` | 查询状态 |
| `GET` | `/api/process/{job_id}/results` | 获取结果 |
| `GET` | `/api/export/{job_id}` | 导出单个任务 |
| `POST` | `/api/export/merge` | 合并导出多个任务 |
| `POST` | `/api/ocr/` | 仅执行 OCR |

## 开发与验证

```bash
PYTHONPATH=backend python3.14 -m unittest discover -s backend/tests -v
python3.14 -m compileall -q backend/app backend/tests
npm --prefix frontend ci
npm --prefix frontend run build
docker compose config --quiet
./scripts/check-public-readiness.sh
```

完整说明见：

- [开发指南](DEVELOPMENT_GUIDE.md)
- [项目沿革与权威边界](docs/HISTORY.md)
- [部署](docs/DEPLOYMENT.md)
- [备份与恢复](docs/BACKUP_AND_RESTORE.md)
- [公开发布检查表](docs/PUBLIC_RELEASE_CHECKLIST.md)

## 许可证

本项目采用 [GNU General Public License v3.0 only](LICENSE)。PDF 渲染由宽松
许可的 `pypdfium2`/PDFium 提供；重新分发镜像或应用包时必须保留其随构建产物
提供的第三方许可文件，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
