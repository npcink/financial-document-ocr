# 部署

## 基本原则

1. 代码、密钥和业务数据分别管理。
2. 候选版本使用独立端口和独立数据目录验证。
3. 新主机从源码构建镜像，不复制依赖目录或旧构建产物。
4. 公网入口必须由反向代理提供 HTTPS、身份认证、限流和访问控制。

## 首次部署

```bash
cp backend/.env.example backend/.env
chmod 600 backend/.env
# 按需配置运行模式、模型和密钥

mkdir -p data/uploads data/exports
chmod 700 data
docker compose config --quiet
docker compose build
docker compose up -d
./scripts/smoke-test.sh http://127.0.0.1:8300
```

## 隔离验证

```bash
HOST_PORT=18000 \
HOST_DATA_DIR=./data-candidate \
COMPOSE_PROJECT_NAME=invoice-ocr-candidate \
docker compose up -d --build

./scripts/smoke-test.sh http://127.0.0.1:18000
```

验证结束后停止候选环境：

```bash
HOST_PORT=18000 \
HOST_DATA_DIR=./data-candidate \
COMPOSE_PROJECT_NAME=invoice-ocr-candidate \
docker compose down
```

## 验收

- Compose 配置通过且容器状态为 `healthy`。
- 首页和静态资源可加载。
- 带测试会话标识的健康接口返回 JSON。
- 重启后数据目录仍可读写。
- 使用人工构造的非真实样例验证上传、OCR、结果查询和导出。
- 日志不包含 OCR 原文、结构化财务字段、密钥或会话标识。

## 回滚

1. 停止新版本。
2. 恢复上一版本代码或镜像。
3. 仅在确认数据库被新版本写坏时恢复已验证的加密快照。
4. 重新运行健康检查和非真实样例测试。
