# 开发指南

## 环境

- Python 3.14
- Node.js 26
- Docker Engine 与 Docker Compose v2

Docker 构建是最终运行基线；宿主机命令用于更快的开发反馈。

## 常用检查

```bash
PYTHONPATH=backend python3.14 -m unittest discover -s backend/tests -v
python3.14 -m compileall -q backend/app backend/tests
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend audit --omit=dev
docker compose config --quiet
docker build -f backend/Dockerfile .
./scripts/check-public-readiness.sh
```

## 开发约束

- 云端与本地驱动保持相同的调用签名、超时和重试语义。
- OCR 与 LLM 并发限制是进程级共享资源，不能为每个任务单独放大。
- 大文件必须流式读写；ZIP 解压必须限制文件数、单文件大小和路径范围。
- 数据库写入通过 `DbConnection` 管理，并保持外键约束和 WAL 配置一致。
- API 返回内容不得包含 API 密钥、内部路径或未处理的异常堆栈。
- 日志不得打印 OCR 原文、结构化财务字段、会话标识或请求认证信息。

## 数据边界

以下内容只能保存在被忽略的运行目录中：

```text
backend/.env
data/jobs.db
data/uploads/
data/exports/
backups/
```

测试使用人工构造的非真实数据。不要把客户、员工、账户、交易或生产日志复制到 fixture、Issue、PR、CI 日志或截图中。

## 变更流程

1. 在独立分支完成修改。
2. 运行与改动相关的单测、编译和前端构建。
3. 运行 `scripts/check-public-readiness.sh` 和 Gitleaks。
4. 涉及 Docker 或依赖时执行完整镜像构建。
5. 涉及 OCR 或导出语义时，用非真实样例完成端到端验证。

部署命令和运行数据不属于源码事实。不要把某一台主机的地址、用户名、目录、端口清单或备份位置写入仓库。
