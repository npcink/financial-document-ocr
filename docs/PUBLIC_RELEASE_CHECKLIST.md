# 公开发布检查表

`v3.0.0` 于 2026-07-21 公开发布时的核验记录：

- [x] `./scripts/check-public-readiness.sh` 通过。
- [x] Gitleaks 对完整 Git 历史和待发布源码包均为 0 命中；被忽略的本机 `.env` 单独保管。
- [x] Git 中没有 `.env`、数据库、上传件、导出件、日志、备份或真实业务样例。
- [x] 文档中没有内部 IP、主机名、用户名、部署路径、备份位置或账户额度。
- [x] Git 作者邮箱符合公开展示预期。
- [x] 云端模型的数据处理和留存说明准确。
- [x] README 和 SECURITY 明确说明当前认证与网络边界。
- [x] npm、Python 依赖审计和 CI 通过。
- [x] 已加入 `GPL-3.0-only` 许可证和 PDF 渲染依赖的第三方许可说明。
- [x] GitHub Secret Scanning、Code Scanning 和分支规则按公开仓库策略启用。
- [x] 从未携带敏感历史的新仓库或新根提交发布。
