# 备份与恢复

## 分离三类内容

| 类型 | 内容 | 默认处理 |
|---|---|---|
| 源码 | 后端、前端、Compose、文档、无密钥模板 | 可进入 Git 和普通源码包 |
| 密钥 | `backend/.env` | 单独加密，文件权限设为 `0600` |
| 业务数据 | SQLite、上传件、导出件 | 单独加密并设置保留期限 |

依赖目录、前端构建产物、Python 缓存和 Docker 构建缓存都可由源码重建，不应进入常规备份。

## 源码备份

```bash
./scripts/backup-source.sh /secure/source-backups
```

脚本生成压缩包和 SHA-256 校验文件。恢复时先校验，再解压：

```bash
shasum -a 256 -c invoice-ocr-source-*.tar.gz.sha256
tar -xzf invoice-ocr-source-*.tar.gz
```

## SQLite 在线备份

```bash
mkdir -p /secure/data-backups
sqlite3 ./data/jobs.db ".backup '/secure/data-backups/jobs-$(date +%Y%m%d-%H%M%S).db'"
chmod 600 /secure/data-backups/jobs-*.db
```

随后使用受信任的加密工具加密快照，并删除未加密中间文件。校验命令：

```bash
sqlite3 /secure/data-backups/jobs-*.db 'PRAGMA integrity_check;'
sqlite3 /secure/data-backups/jobs-*.db 'PRAGMA foreign_key_check;'
```

不要单独复制 `jobs.db-wal` 或 `jobs.db-shm` 到另一台设备。

## 恢复

1. 停止应用，避免恢复过程中继续写入。
2. 为当前数据库创建加密快照。
3. 对候选快照执行完整性和外键检查。
4. 恢复为 `data/jobs.db`，权限设为 `0600`。
5. 启动应用，检查健康状态、任务读取和导出行为。

## 密钥

解密后的环境文件放在 `backend/.env`：

```bash
chmod 600 backend/.env
docker compose config --quiet
```

不要把 `docker compose config` 的完整展开结果粘贴到公开日志，因为其中可能包含环境变量值。
