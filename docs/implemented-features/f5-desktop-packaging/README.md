# F5: 跨平台桌面应用打包与发布

## 功能概述

将 Cerebro 打包为 macOS / Windows / Linux 三平台可分发的桌面应用：系统托盘常驻、
Ollama 依赖引导与模型预热、GitHub Actions 打 tag 自动构建并发布安装包。

## 实施状态

**状态**: ✅ 已完成（首版 v0.0.1 起，持续迭代至 v0.0.13）
**原设计**: [DESIGN.md](DESIGN.md)（2026-06-12 编写，编号原为 F4）

> 编号说明：原 `future-feature-design/README.md` 中本功能编号为 F4，与已归档的
> `f4-command-recommender` 冲突，归档时统一重编号为 F5。

## 实现记录（与原设计的差异）

| 原设计 | 实际实现 |
|---|---|
| `main.spec` + `desktop.spec` 两个 spec | 单一 `packaging/cerebro.spec`（入口 `launcher.py`，onedir，macOS `BUNDLE` → `Cerebro.app`，`LSUIElement=True`，Windows 版本信息由 `APP_VERSION` 注入） |
| `scripts/build_{all,macos,linux}.sh` / `build_windows.bat` | 无本地构建脚本；统一由 CI 执行 `pyinstaller packaging/cerebro.spec --noconfirm` |
| macOS `.pkg`（packagesbuild/pkgbuild） | **`.dmg`**（`packaging/macos_package.sh`，ad-hoc `codesign` + `create-dmg`/`hdiutil`），`entitlements.plist` |
| Windows Inno Setup 或 NSIS | **Inno Setup**（`packaging/installer.iss`，中文语言包 `ChineseSimplified.isl`），可选"开机自启"任务写 `HKCU\...\Run` |
| Linux `.deb` / `.rpm`（FPM）、systemd、Docker | **AppImage**（`packaging/linux_package.sh`）；未做 deb/rpm/systemd/Docker |
| `desktop_app.py` 托盘 + 自启动 + 状态监控 | `src/desktop_app.py`：`TrayApp`（pystray 菜单：打开 CLI / 打开 Web UI / 检查状态 / 模型预热 / 重启 / 退出）、`StatusMonitor`、`OllamaWarmer`、`LogManager`；`--tray` / `--warm-up` / `--status` 参数 |
| 各平台自启动（launchd / 注册表 / systemd） | 仅 Windows 安装器可选任务；`AppConfig.autostart` 配置项存在但未生效；macOS/Linux 未实现 |
| `dependency_checker.py` 检测 Python/Ollama/Tesseract | `src/bootstrap.py::ensure_ollama_ready`：检测 / 安装 / 启动 Ollama、拉取缺失模型；**不含 Tesseract**（仅开发者脚本 `scripts/check_prereqs.*` 检测） |
| `updater.py` 应用内自动更新 | 未实现（Release 附 `SHA256SUMS`）。已决定不做应用内自更新，降级为"启动时检查新版本并提示"（见 future-feature-design） |
| GitHub Actions release 工作流 | `.github/workflows/release.yml`：`v*` tag → prepare / build-windows / build-macos / build-linux / release（自动生成 Release Notes、SHA256SUMS）/ changelog（归档 `[Unreleased]` 并开 PR）。另有 `ci.yml`、`pr-build-vulnerability-gate.yml` |
| 正式代码签名与公证 | 仅 ad-hoc 签名；未接入 Apple Developer / Windows 代码签名证书 |
| 应用商店发布、插件系统、云同步、GUI 配置窗口 | 取消：商店与云同步违背本地优先定位；GUI 配置由 Web UI（F7）替代 |

## 启动方式

| 命令 | 行为 |
|---|---|
| `python launcher.py`（或双击应用） | 默认托盘 GUI，含 Ollama 引导 |
| `python launcher.py --cli` / `chat` | CLI 交互界面 |
| `python launcher.py --web` | Gradio Web 界面（127.0.0.1:7860） |
| `python launcher.py --skip-bootstrap` | 跳过 Ollama 引导 |

## 相关文档

- [DESIGN.md](DESIGN.md) - 原始设计方案
- [docs/CI_CD.md](../../CI_CD.md) - CI/CD 与发布流程
- [SIMPLE_DESIGN.md](SIMPLE_DESIGN.md) - 被采纳的单文件托盘方案原始设计（类结构与 `src/desktop_app.py` 对应；其中的自启动参数未实现，模型名已过时）

## 遗留事项

已收拢到 [docs/future-feature-design/README.md](../../future-feature-design/README.md)「残留小项」：
启动时检查新版本提示、macOS/Linux 自启动、Tesseract 引导。
