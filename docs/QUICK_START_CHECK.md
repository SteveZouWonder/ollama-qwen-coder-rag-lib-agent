# 前置条件检查快速指南

本指南帮助您快速验证和配置项目运行所需的前置条件。

## 一键检查

### Linux/macOS 用户

```bash
./check_prereqs.sh
```

### Windows 用户

```powershell
.\check_prereqs.ps1
```

## 检查结果说明

- 🟢 **绿色 (✓)**: 条件满足，可以继续
- 🔴 **红色 (✗)**: 条件缺失，必须解决
- 🟡 **黄色 (⚠)**: 警告项（可选，但推荐解决）

## 常见问题快速解决

### 1. Python版本过低

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.9

# macOS
brew install python@3.9

# 验证
python3 --version
```

### 2. Ollama服务未运行

```bash
# 启动Ollama服务
ollama serve

# 或后台运行
nohup ollama serve > ollama.log 2>&1 &

# 验证
curl http://localhost:11434/api/tags
```

### 3. 模型未下载

```bash
# 下载主模型
ollama pull qwen2.5-coder:7b

# 下载嵌入模型
ollama pull nomic-embed-text:latest

# 验证
ollama list
```

### 4. Python依赖缺失或环境不一致

**诊断问题：**
```bash
# 运行详细依赖验证脚本
./verify_deps.sh

# 这会显示：
# - 当前使用的Python环境
# - 已安装的Python包列表
# - 模块导入测试结果
```

**推荐方法：使用专用安装脚本（解决依赖冲突）**
```bash
./install_deps.sh      # Linux/macOS
.\install_deps.ps1     # Windows PowerShell
```

**标准方法：**
```bash
pip install -r requirements.txt
```

**虚拟环境问题：**
```bash
# 如果install_deps.sh成功但check_prereqs.sh失败，可能是虚拟环境不一致

# 检查当前环境
echo $VIRTUAL_ENV

# 激活虚拟环境
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate  # Windows

# 重新验证
./check_prereqs.sh
```

**如果遇到依赖冲突：**
这是因为依赖冲突导致的，请：
1. 使用提供的 `install_deps.sh` 脚本（推荐）
2. 或按顺序手动安装：先安装banks，再安装其他依赖
3. 创建全新的虚拟环境重新开始

### 5. 网络连接问题

```bash
# 检查网络连接
ping ollama.com

# 使用代理（如果需要）
export HTTP_PROXY=http://your-proxy:port
export HTTPS_PROXY=http://your-proxy:port
```

### 6. ChromaDB遥测错误

**症状**: 运行时出现以下错误：
```
Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument but 3 were given
Failed to send telemetry event ClientCreateCollectionEvent: capture() takes 1 positional argument but 3 were given
```

**快速解决方案：**
```bash
# 项目代码已自动禁用遥测，如仍遇到错误：

# 方案1：设置环境变量
export ANONYMIZED_TELEMETRY=False
export CHROMA_TELEMETRY=False

# 方案2：降级ChromaDB
pip install chromadb==0.4.22

# 方案3：更新代码
git pull  # 获取最新修复
```

**注意**: 此错误不影响核心功能，只是显示错误信息。

### 6. urllib3 OpenSSL警告（macOS）

**症状**: 在macOS上出现OpenSSL版本警告：
```
NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+, currently the 'ssl' module is compiled with LibreSSL 2.8.3
```

**快速解决方案**:
```bash
# 项目已自动禁用此警告，如仍看到：

# 方案1：降级urllib3
pip install "urllib3<2.0.0"

# 方案2：更新代码获取最新修复
git pull && pip install -r requirements.txt
```

**注意**: 此警告只影响显示，不影响功能。

## 手动验证清单

如果自动检查脚本无法运行，可以手动验证以下项目：

### ✅ Python环境
```bash
python3 --version  # 应该 >= 3.8
```

### ✅ pip工具
```bash
pip3 --version
```

### ✅ Ollama服务
```bash
ollama --version
curl http://localhost:11434/api/tags  # 应该返回JSON
```

### ✅ 必需模型
```bash
ollama list | grep qwen2.5-coder    # 应该显示模型
ollama list | grep nomic-embed-text # 应该显示模型
```

### ✅ Python依赖
```bash
python3 -c "import llama_index, chromadb, rich"
```

## 详细文档

更详细的配置说明请参考：
- [详细使用教程 - 前置条件检查与配置章节](TUTORIAL.md#前置条件检查与配置)
- [详细使用教程 - 安装指南章节](TUTORIAL.md#安装指南)
- [详细使用教程 - 故障排除章节](TUTORIAL.md#故障排除)

## 获取帮助

如果以上方法都无法解决问题，请：

1. 检查系统日志: `cat ~/.ollama/logs/server.log`
2. 验证系统资源: `free -h` (Linux) 或 `系统信息` (Windows)
3. 查看Python错误: `python3 -c "import sys; sys.exit(0)"`

完成所有检查后，即可开始使用项目：
```bash
python query_interface.py --data ./data
```