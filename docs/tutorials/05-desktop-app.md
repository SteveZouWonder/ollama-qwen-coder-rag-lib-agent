# 桌面应用使用指南

> 桌面应用提供配置管理、模型预热、状态监控等便捷功能。

---

## 概述

桌面应用（`desktop_app.py`）为 Ollama 服务提供便捷的管理功能，包括：

- 📊 实时状态监控
- 🔥 自动模型预热
- ⚙️ 配置文件管理
- 🖥️ 系统托盘支持（可选）
- 📝 日志记录和管理

---

## 安装

桌面应用是项目的一部分，无需额外安装。如果需要系统托盘功能，需要安装可选依赖：

```bash
# 基础功能（无需额外依赖）
python desktop_app.py --status
python desktop_app.py --warm-up

# 系统托盘功能（可选）
pip install pystray pillow
python desktop_app.py --tray
```

---

## 配置文件

桌面应用使用 JSON 配置文件，默认位置为 `config/app_config.json`。

**默认配置**:
```json
{
  "ollama_base_url": "http://localhost:11434",
  "models_to_warm_up": [
    "nomic-embed-text:latest",
    "qwen2.5-coder:7b"
  ],
  "check_interval": 600,
  "warm_up_on_startup": false,
  "autostart": false
}
```

**配置项说明**:

| 配置项 | 类型 | 说明 | 默认值 |
|-------|------|------|--------|
| `ollama_base_url` | string | Ollama 服务地址 | `http://localhost:11434` |
| `models_to_warm_up` | array | 需要预热的模型列表 | `["nomic-embed-text:latest", "qwen2.5-coder:7b"]` |
| `check_interval` | integer | 状态检查间隔（秒） | `600` |
| `warm_up_on_startup` | boolean | 启动时是否自动预热 | `false` |
| `autostart` | boolean | 是否开机自启（未实现） | `false` |

---

## 命令行功能

### 1. 状态检查

检查 Ollama 服务状态和已加载的模型：

```bash
python desktop_app.py --status
```

**输出示例**:
```
========== Ollama 服务状态 ==========
Ollama服务: ✅ 正常
已加载模型: nomic-embed-text:latest, qwen2.5-coder:7b
```

### 2. 模型预热

预热配置的模型，减少首次查询的延迟：

```bash
python desktop_app.py --warm-up
```

**输出示例**:
```
开始预热 2 个模型...
预热 nomic-embed-text:latest: ✅ 成功
预热 qwen2.5-coder:7b: ✅ 成功
所有模型预热完成！
```

### 3. 系统托盘（可选）

启动系统托盘应用，提供图形界面操作：

```bash
python desktop_app.py --tray
```

**功能**:
- 系统托盘图标
- 右键菜单：查看状态、预热模型、打开终端、退出
- 状态显示和日志查看

**注意**: 系统托盘功能需要安装 `pystray` 和 `pillow` 依赖，且仅在支持GUI的环境（Windows、macOS、Linux桌面）中可用。

### 4. 帮助信息

显示命令行帮助：

```bash
python desktop_app.py --help
```

---

## 使用场景

### 场景1: 开发前准备

每次开发前预热模型，确保查询响应快速：

```bash
# 检查服务状态
python desktop_app.py --status

# 预热模型
python desktop_app.py --warm-up

# 开始使用
python query_interface.py --data ./data
```

### 场景2: 定期监控

定期检查服务状态，确保服务正常运行：

```bash
# 添加到 crontab (每10分钟检查一次)
*/10 * * * * cd /path/to/project && python desktop_app.py --status >> /var/log/ollama_status.log 2>&1
```

### 场景3: 系统托盘常驻

在支持GUI的环境中，使用系统托盘应用：

```bash
# 启动托盘应用
python desktop_app.py --tray

# 通过托盘菜单操作
# - 查看状态
# - 预热模型
# - 打开终端
# - 退出应用
```

---

## 日志管理

桌面应用自动记录日志到 `logs/` 目录：

- **应用日志**: `logs/app.log` - 应用运行日志
- **状态日志**: `logs/status.log` - Ollama 服务状态记录
- **预热日志**: `logs/warmup.log` - 模型预热记录

**查看日志**:
```bash
# 查看应用日志
tail -f logs/app.log

# 查看状态日志
tail -f logs/status.log

# 查看预热日志
tail -f logs/warmup.log
```

---

## 故障排除

### 问题1: 无法连接到 Ollama 服务

**错误信息**:
```
❌ Ollama服务: ❌ 无法连接
```

**解决方案**:
1. 检查 Ollama 服务是否运行:
   ```bash
   ps aux | grep ollama
   ```
2. 检查配置文件中的 URL 是否正确:
   ```bash
   cat config/app_config.json
   ```
3. 尝试手动连接测试:
   ```bash
   curl http://localhost:11434/api/tags
   ```

### 问题2: 模型预热失败

**错误信息**:
```
预热 qwen2.5-coder:7b: ❌ 失败 - 错误信息
```

**解决方案**:
1. 检查模型是否已拉取:
   ```bash
   ollama list
   ```
2. 手动拉取模型:
   ```bash
   ollama pull qwen2.5-coder:7b
   ```
3. 检查磁盘空间是否充足:
   ```bash
   df -h
   ```

### 问题3: 系统托盘功能不可用

**错误信息**:
```
❌ 桌面支持未安装，请安装 pystray 和 pillow
```

**解决方案**:
1. 安装GUI依赖:
   ```bash
   pip install pystray pillow
   ```
2. 确认在支持GUI的环境中运行
3. 如果不需要GUI功能，使用命令行参数即可

---

## 高级配置

### 自定义配置文件

使用自定义配置文件位置：

```bash
# 修改代码中的配置文件路径，或
# 设置环境变量（需要修改代码支持）
```

### 添加更多模型到预热列表

编辑 `config/app_config.json`:

```json
{
  "models_to_warm_up": [
    "nomic-embed-text:latest",
    "qwen2.5-coder:7b",
    "llama3:8b",
    "mistral:7b"
  ]
}
```

### 调整检查间隔

根据需求调整状态检查间隔：

```json
{
  "check_interval": 300
}
```

---

## 最佳实践

1. **定期预热**: 在每次开发前预热模型，确保快速响应
2. **状态监控**: 定期检查服务状态，及时发现和解决问题
3. **日志查看**: 定期查看日志，了解应用运行情况
4. **配置备份**: 备份配置文件，便于恢复和迁移
5. **资源管理**: 根据系统资源调整预热模型列表和检查间隔

---

## 与其他功能集成

### 与 RAG 引擎集成

在使用 RAG 引擎前预热模型：

```bash
# 预热模型
python desktop_app.py --warm-up

# 启动 RAG 引擎
python query_interface.py --data ./data
```

### 与 Agent 集成

在使用 Agent 前检查服务状态：

```bash
# 检查状态
python desktop_app.py --status

# 启动 Agent
python query_interface.py --agent "你的任务"
```

---

**上一篇**: [详细功能说明](04-features.md) | **下一篇**: [故障排除](06-troubleshooting.md)