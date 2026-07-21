# 公开发布检查表

将仓库可见性改为 Public 前，逐项确认：

- [ ] `./scripts/check-public-readiness.sh` 通过。
- [ ] Gitleaks 对完整 Git 历史和待发布源码包均为 0 命中；被忽略的本机 `.env` 单独保管。
- [ ] Git 中没有 `.env`、数据库、上传件、导出件、日志、备份或真实业务样例。
- [ ] 文档中没有内部 IP、主机名、用户名、部署路径、备份位置或账户额度。
- [ ] Git 作者邮箱符合公开展示预期。
- [ ] 云端模型的数据处理和留存说明准确。
- [ ] README 和 SECURITY 明确说明当前认证与网络边界。
- [ ] npm、Python 依赖审计和 CI 通过。
- [ ] 已选择并加入适当的开源许可证。
- [ ] GitHub Secret Scanning、Code Scanning 和分支规则按公开仓库策略启用。
- [ ] 从未携带敏感历史的新仓库或新根提交发布。
