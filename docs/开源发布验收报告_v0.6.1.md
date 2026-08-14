# 开源转正验收报告 · text-cleaning-engine v0.6.1

> 验收标准：GitHub 主流开源项目规范（转正模板硬门槛 + 加分项）
> 日期：2026-08-13

## 硬门槛

| 检查项 | 状态 | 证据 |
|--------|:---:|------|
| 代码结构：无根目录散落死代码 | ✅ | `cleaner/` + `cli/` + `rules/` + `tests/` 分层，零死代码；入口统一 `python cli/clean_batch.py` / `python -m cleaner.cleaning` |
| 隐私安全：无硬编码密钥/绝对路径 | ✅ | 全仓复扫 0 命中；工具路径全走 `.env` 环境变量 |
| 文档：README 中英双语 | ✅ | README.md / README_zh.md（徽章/特性/安装/配置/CLI/测试/FAQ） |
| 文档：CHANGELOG Keep-a-Changelog | ✅ | CHANGELOG.md / CHANGELOG_zh.md，版本史 0.1→0.6.1 连续 |
| 文档：LICENSE | ✅ | AGPL-3.0 + COMMERCIAL.md 双许可 |
| 文档：CONTRIBUTING.md | ✅ | 已有 |
| 文档：CODE_OF_CONDUCT.md | ✅ | 本轮新增（Contributor Covenant 2.1） |

## 加分项

| 检查项 | 状态 | 证据 |
|--------|:---:|------|
| 测试 + CI | ✅ | `tests/` 套件（保留率门禁 100%、验收 8/8、10 轮 295/295）+ `.github/workflows/ci.yml`（Python 3.10/3.11/3.12） |
| 发布：Git tag + GitHub Release | ✅ | v0.6.1 已打 tag，GitHub Release 已发布 |
| 社区：issue/PR 模板 | ✅ | 本轮新增 bug_report / feature_request / PULL_REQUEST_TEMPLATE |
| 社区：SECURITY.md | ✅ | 已有 |

## 自查

- [x] `python tests/test_teaching_retention.py` 通过（保留率 100%）
- [x] git status 干净
- [x] 无敏感信息残留
