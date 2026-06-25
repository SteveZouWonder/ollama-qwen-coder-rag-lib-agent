# 更新日志

本项目所有重要变更都记录在本文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

> 下一版本的未发布变更请记录在此区段。发布时将其移动到对应的版本号下。

## [v0.0.5] - 2026-06-25

### 新增
- README 顶部新增 CLI 三模式演示 GIF 与桌面应用演示 GIF
- 新增演示 GIF 生成脚本 `docs/assets/demo_script.sh`

### 改进
- 优化 README 首屏：居中布局、项目定位副标题、徽章、四大卖点与快捷导航
- CLI 启动 banner 改用 Cerebro ASCII 艺术字，与 README/演示 GIF 视觉统一
- 纯文本（无 Rich）环境的 banner 保留 `Cerebro` 产品名，提升可读性

### 发布流程
- Release Notes 改为从 CHANGELOG 提取当前版本正文（关闭 GitHub 自动 PR 汇总），使发布说明与 CHANGELOG 内容一致；未归档时回退提取 `[Unreleased]`
- Release 正文末尾保留「完整对比」链接（自动计算上一个版本 tag）

## [v0.0.4] - 2026-06-24

### 发布流程
- 重写 CHANGELOG 对齐真实发布标签（v0.0.1 ~ v0.0.3）
- Release Notes 改为由 GitHub 自动汇总 commit/PR，并附固定安装说明
- Release 流程新增版本号一致性校验（tag 与手动输入对齐）
- 新增 `scripts/bump_changelog.py`，支持归档 `[Unreleased]` 与提取版本正文
- 发布时（推送 `v*` tag）自动归档 CHANGELOG 并创建 PR，由人工审核合并到 `master`

## [v0.0.3] - 2026-06-24

### 新增
- 新增 `AGENTS.md`，定义强制性的 Git 工作流规则（禁止直接提交 master、改动前确认分支、完成后确认 PR）

### 修复
- 修复打包后应用在知识库未初始化时执行 `/ask` 导致崩溃的问题
- 打包模式下将运行时数据路径统一收敛到用户数据目录，避免写入只读的应用目录

## [v0.0.2] - 2026-06-24

### 修复
- 修复打包后应用的 GUI 启动卡死与 Ollama 检测失败问题
- 修复 macOS 应用包版本号未与 `APP_VERSION`（发布 tag）同步的问题

### 改进
- 将版本号嵌入 Windows exe 与 Linux AppImage 的元数据中

## [v0.0.1] - 2026-06-23

### 新增
- 首个公开发布版本：本地 RAG + 代码助手（基于 Ollama `qwen2.5-coder`）
- 三平台桌面安装包：Windows 安装器、macOS DMG、Linux AppImage
- 完整的发布流程（GitHub Actions：推送 `v*` tag 自动构建并发布到 Release）

### 修复
- 修复 CI/CD 流水线中的构建与测试任务失败问题
- 移除 `desktop_app.py` 中 `subprocess.Popen` 的 `shell=True`，消除 bandit HIGH (B602) 告警

### 安全
- 在依赖审计中忽略 chromadb 的 CVE-2026-45829（项目未启用 `trust_remote_code`，且暂无修复版本）

---

## 版本号规则

- **主版本号（MAJOR）**：包含不兼容的重大架构变更
- **次版本号（MINOR）**：向后兼容的新功能
- **修订号（PATCH）**：向后兼容的缺陷修复

## 发布说明

每次发布由推送 `v<MAJOR>.<MINOR>.<PATCH>` 标签触发，GitHub Actions 会自动：

1. 解析标签得到版本号（并校验语义化版本格式）
2. 并行构建 Windows / macOS / Linux 三平台安装包
3. 汇总产物并创建 GitHub Release（从 CHANGELOG 提取本版本正文作为 Release Notes + 安装说明 + SHA256 校验和 + 完整对比链接）
4. 自动归档 CHANGELOG：把 `[Unreleased]` 归档为该版本号，提交到新分支并创建 PR

> Release Notes 的「本次变更」来自 CHANGELOG 当前版本区段（若发布时尚未归档则取 `[Unreleased]`），
> 因此请在发布前把变更写清楚，确保 Release 页面展示与 CHANGELOG 一致。

平时把变更写入 `[Unreleased]` 区段即可；发布时归档由 CI 自动完成，
生成的 PR 需人工审核后合并到 `master`。也可在本地手动归档预览：

```bash
# 预览归档结果（不写文件）
python scripts/bump_changelog.py bump --version 1.0.0 --dry-run
# 实际归档
python scripts/bump_changelog.py bump --version 1.0.0
```
