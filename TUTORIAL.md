# 智能文档+代码助手 - 详细使用教程

> 基于 Ollama qwen2.5-coder:7b 的融合型 AI 助手，同时支持 RAG 知识库检索和 ReAct Agent 代码操作。

---

## 目录

1. [项目概述](#项目概述)
2. [系统要求](#系统要求)
3. [前置条件检查与配置](#前置条件检查与配置)
4. [安装指南](#安装指南)
5. [配置说明](#配置说明)
6. [快速开始](#快速开始)
7. [详细功能说明](#详细功能说明)
8. [高级用法](#高级用法)
9. [知识库智能优化](#知识库智能优化)
10. [安全机制](#安全机制)
11. [故障排除](#故障排除)
12. [最佳实践](#最佳实践)

---

## 项目概述

### 核心功能

这个项目将两个强大的AI功能融合在一个统一的CLI界面中：

- **📚 RAG 知识库查询**: 基于上传的PDF、论文、笔记、代码等文档进行语义检索和问答
- **🤖 ReAct Agent 任务**: 通过Thought → Action → Observe循环自动执行复杂的代码任务

### 技术架构

```
统一CLI界面 (query_interface.py)
    ├── RAG引擎 (rag_engine.py) - 语义检索 + 来源追溯
    ├── ReAct引擎 (react_engine.py) - 自动工具调用 + 安全护栏
    └── 工具链 (agent_tools.py) - 文件/命令/搜索操作
         ↓
    Ollama qwen2.5-coder:7b (统一LLM)
    + nomic-embed-text (语义编码)
```

### 适用场景

#### 🎓 学术研究场景

**论文阅读与理解**
- 查询论文中的核心贡献和创新点
- 总结研究方法论和实验结果
- 对比多篇论文的观点和差异
- 提取论文中的关键数据和结论

**笔记管理**
- 整理学习笔记中的关键概念
- 跨文档查询相关知识点
- 生成复习提纲和知识图谱
- 回答基于笔记的具体问题

**文献综述**
- 快速浏览多篇文献的核心内容
- 按主题组织文献观点
- 识别研究趋势和热点
- 辅助写作文献综述

#### 💻 代码开发场景

**自动化代码生成**
- 根据需求描述生成完整的功能代码
- 实现复杂算法和数据结构
- 创建测试用例和示例代码
- 生成API接口文档

**代码重构与优化**
- 重构遗留代码，提高可读性
- 优化性能瓶颈和内存使用
- 统一代码风格和规范
- 减少代码重复，提取公共函数

**调试与测试**
- 自动化测试用例生成
- 运行单元测试并分析结果
- 定位和修复bug
- 生成错误日志分析报告

#### 📚 文档分析场景

**技术文档理解**
- 快速理解复杂的技术文档
- 提取配置参数和使用说明
- 生成操作步骤指南
- 回答基于文档的疑问

**API文档查询**
- 查询API的具体用法
- 理解接口参数和返回值
- 生成API调用示例
- 对比不同版本的API差异

**项目文档管理**
- 整理项目文档结构
- 搜索相关文档内容
- 生成文档索引和目录
- 保持文档与代码同步

#### 🛠️ 项目维护场景

**代码搜索与分析**
- 搜索项目中的特定功能实现
- 分析代码调用关系
- 查找硬编码的配置项
- 定位安全漏洞和风险点

**日常维护任务**
- 批量重命名和重构
- 更新依赖包版本
- 清理无用代码和文件
- 自动化部署脚本生成

**代码审查辅助**
- 检查代码质量
- 识别潜在问题
- 提供改进建议
- 生成审查报告

#### 🎯 数据分析与处理

**数据集分析**
- 分析数据集的统计特征
- 生成数据探索报告
- 识别异常值和模式
- 建议数据处理方法

**日志文件处理**
- 分析服务器日志
- 提取错误信息和警告
- 生成监控报告
- 识别性能问题

**配置文件管理**
- 统一配置格式
- 生成配置模板
- 验证配置正确性
- 迁移配置到新版本

#### 📖 学习与培训

**新知识学习**
- 快速理解新技术概念
- 解释复杂的技术术语
- 提供学习路径建议
- 生成练习题和答案

**团队培训**
- 创建培训材料
- 生成代码示例和教程
- 解答技术疑问
- 提供实践项目建议

**技能提升**
- 分析代码最佳实践
- 提供代码改进建议
- 介绍设计模式和架构
- 推荐学习资源

#### 🔍 质量保证

**自动化测试**
- 生成单元测试代码
- 创建集成测试用例
- 模拟测试数据
- 生成测试覆盖率报告

**代码规范检查**
- 检查代码风格一致性
- 验证命名规范
- 检测代码异味
- 生成改进建议

**性能优化**
- 分析代码性能瓶颈
- 优化算法复杂度
- 减少内存使用
- 提供优化建议

#### 🚀 DevOps与运维

**自动化脚本**
- 生成部署脚本
- 创建监控脚本
- 备份和恢复脚本
- 日志分析脚本

**配置管理**
- 统一配置格式
- 生成配置模板
- 验证配置正确性
- 配置版本对比

**故障排查**
- 分析错误日志
- 诊断系统问题
- 提供解决方案
- 生成故障报告

---

## 系统要求

### 硬件要求

- **CPU**: 4核心以上推荐
- **内存**: 8GB以上（16GB推荐）
- **存储**: 至少10GB可用空间（用于模型和索引）

### 软件要求

- **操作系统**: Linux、macOS、Windows (WSL2)
- **Python**: 3.8或更高版本
- **Ollama**: 最新版本
- **Git**: 用于版本控制（可选）

### 网络要求

- **互联网连接**: 首次运行需要下载模型和依赖包
- **代理设置**: 如果使用代理，需要正确配置环境变量
- **防火墙**: Ollama默认使用11434端口，需要确保端口可访问

---

## 前置条件检查与配置

### 前置条件总览

在启动本程序之前，必须确保以下所有前置条件都已正确配置：

| 前置条件 | 必需性 | 版本要求 | 验证方法 |
|---------|--------|----------|----------|
| Python环境 | 必需 | 3.8+ | `python3 --version` |
| Ollama服务 | 必需 | 最新版 | `ollama list` |
| qwen2.5-coder模型 | 必需 | 7b版本 | `ollama show qwen2.5-coder:7b` |
| nomic-embed-text模型 | 必需 | latest | `ollama show nomic-embed-text:latest` |
| Python依赖 | 必需 | 见requirements.txt | `pip list` |
| 系统内存 | 必需 | 8GB+ | `free -h` / `系统信息` |
| 磁盘空间 | 必需 | 10GB+ | `df -h` |
| Git工具 | 可选 | 任意版本 | `git --version` |

### 前置条件检查清单

#### 1. Python环境检查

**检查Python版本:**
```bash
# 检查Python是否安装
python3 --version
# 或
python --version

# 验证版本是否符合要求 (需要3.8+)
python3 -c "import sys; print(f'Python {sys.version}'); exit(0 if sys.version_info >= (3, 8) else 1)"
```

**如果Python未安装或版本过低:**

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.9 python3-pip python3-venv
```

**macOS (使用Homebrew):**
```bash
brew install python@3.9
```

**CentOS/RHEL:**
```bash
sudo yum install python39 python39-pip python39-devel
```

**Windows:**
```powershell
# 从 https://www.python.org/downloads/ 下载安装Python 3.8+
# 安装时勾选 "Add Python to PATH"
```

#### 2. Ollama服务检查

**检查Ollama是否安装:**
```bash
# 检查Ollama命令是否可用
which ollama
# 或
where ollama  # Windows

# 检查Ollama版本
ollama --version
```

**检查Ollama服务状态:**
```bash
# 查看Ollama服务是否运行
ps aux | grep ollama  # Linux/macOS
# 或
tasklist | findstr ollama  # Windows

# 检查Ollama服务端口
netstat -tuln | grep 11434  # Linux
lsof -i :11434  # macOS
netstat -an | findstr 11434  # Windows
```

**如果Ollama未安装:**

**Linux/macOS:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
```powershell
# 下载安装包
# 访问 https://ollama.com/download
# 运行安装程序
```

**如果Ollama服务未运行:**

**Linux (systemd):**
```bash
sudo systemctl start ollama
sudo systemctl enable ollama  # 设置开机自启
sudo systemctl status ollama  # 检查状态
```

**macOS (Homebrew):**
```bash
brew services start ollama
brew services list  # 查看服务状态
```

**手动启动Ollama:**
```bash
# 前台运行（用于调试）
ollama serve

# 后台运行
nohup ollama serve > ollama.log 2>&1 &
```

#### 3. 模型下载和验证

**下载所需模型:**
```bash
# 下载主模型 (约4-5GB)
ollama pull qwen2.5-coder:7b

# 下载嵌入模型 (约200MB)
ollama pull nomic-embed-text:latest

# 验证模型下载
ollama list
```

**验证模型完整性:**
```bash
# 检查模型详细信息
ollama show qwen2.5-coder:7b
ollama show nomic-embed-text:latest

# 测试模型是否正常工作
echo "测试模型连接..." | ollama run qwen2.5-coder:7b "请回答：1+1等于几？"
```

**如果模型下载失败:**

**检查网络连接:**
```bash
# 测试网络连接
ping ollama.com
curl -I https://ollama.com

# 如果使用代理
export HTTPS_PROXY=http://your-proxy:port
export HTTP_PROXY=http://your-proxy:port
ollama pull qwen2.5-coder:7b
```

**手动下载模型文件:**
```bash
# 从镜像站下载（如果有）
# 或使用其他下载工具后手动导入
```

#### 4. 系统资源检查

**检查内存使用:**
```bash
# Linux
free -h
# 确保可用内存 > 8GB

# macOS
vm_stat
top -o mem

# Windows
systeminfo
```

**检查磁盘空间:**
```bash
# Linux/macOS
df -h
# 确保至少有10GB可用空间

# Windows
dir
wmic logicaldisk get size,freespace,caption
```

**检查CPU资源:**
```bash
# Linux
lscpu
nproc

# macOS
sysctl -n hw.ncpu

# Windows
wmic cpu get NumberOfLogicalProcessors
```

#### 5. Python依赖安装

**创建虚拟环境（强烈推荐）:**
```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 升级pip
pip install --upgrade pip
```

**安装项目依赖:**
```bash
# 进入项目目录
cd ollama-qwen-coder-rag-lib

# 安装依赖
pip install -r requirements.txt

# 验证安装
pip list
```

**如果依赖安装失败:**

**使用国内镜像源:**
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**逐个安装依赖:**
```bash
pip install llama-index>=0.10.0
pip install llama-index-embeddings-ollama>=0.1.0
pip install llama-index-llms-ollama>=0.1.0
pip install llama-index-readers-file>=0.1.0
pip install llama-index-vector-stores-chroma>=0.1.0
pip install chromadb>=0.4.0
pip install pypdf>=4.0.0
pip install requests>=2.31.0
pip install python-dotenv>=1.0.0
pip install rich>=13.0.0
pip install prompt-toolkit>=3.0.0
```

#### 6. 网络和防火墙配置

**检查Ollama端口:**
```bash
# 测试本地Ollama服务
curl http://localhost:11434/api/tags

# 如果失败，检查防火墙设置
```

**配置防火墙:**

**Linux (ufw):**
```bash
sudo ufw allow 11434/tcp
sudo ufw reload
```

**Linux (firewalld):**
```bash
sudo firewall-cmd --permanent --add-port=11434/tcp
sudo firewall-cmd --reload
```

**macOS:**
```bash
# 系统偏好设置 -> 安全性与隐私 -> 防火墙
# 添加Ollama到允许列表
```

**Windows:**
```powershell
# Windows Defender 防火墙 -> 允许应用通过防火墙
# 添加Ollama的入站规则
```

#### 7. 环境变量配置

**创建环境变量文件:**
```bash
# 在项目根目录创建 .env 文件
cat > .env << EOF
# Ollama配置
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=qwen2.5-coder:7b
EMBED_MODEL=nomic-embed-text:latest

# RAG配置
CHUNK_SIZE=1024
CHUNK_OVERLAP=200
TOP_K=5
SIMILARITY_CUTOFF=0.7

# Agent配置
MAX_HISTORY=100
MAX_ITERATIONS=50
TIMEOUT=300
CODE_AGENT_AUTO_CONFIRM=false
EOF

# 设置文件权限（保护敏感信息）
chmod 600 .env
```

**加载环境变量:**
```bash
# 方式1：使用python-dotenv（推荐）
# 程序会自动加载 .env 文件

# 方式2：手动导出
export OLLAMA_BASE_URL=http://localhost:11434
export LLM_MODEL=qwen2.5-coder:7b
export EMBED_MODEL=nomic-embed-text:latest

# 方式3：在 ~/.bashrc 或 ~/.zshrc 中添加
echo 'export OLLAMA_BASE_URL=http://localhost:11434' >> ~/.bashrc
source ~/.bashrc
```

### 自动化前置条件检查脚本

本项目提供了两个自动化检查脚本，可以一键验证所有前置条件：

#### Linux/macOS 用户

```bash
# 运行检查脚本
./check_prereqs.sh

# 赋予执行权限（如果尚未执行）
chmod +x check_prereqs.sh
```

#### Windows 用户

```powershell
# 在PowerShell中运行
.\check_prereqs.ps1

# 如果遇到执行策略限制，先运行：
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### 检查脚本功能

检查脚本会自动验证：

- ✅ Python环境（版本3.8+）
- ✅ Ollama服务状态
- ✅ 必需模型是否已下载
- ✅ Python依赖包是否安装
- ✅ 系统资源（内存、磁盘）
- ✅ 网络连接
- ✅ 项目文件完整性

检查结果：
- 🟢 **绿色**：条件满足
- 🔴 **红色**：条件缺失，必须解决
- 🟡 **黄色**：警告项（可选）

**使用建议**：
- 首次使用前务必运行检查脚本
- 更新依赖后重新运行检查
- 遇到问题时首先运行检查脚本诊断

### 不同操作系统的特殊配置

#### Windows系统配置

**WSL2安装（推荐）:**
```powershell
# 在PowerShell中运行（管理员）
wsl --install

# 重启后，在WSL2中安装Ubuntu
# 然后按照Linux的配置步骤进行
```

**原生Windows配置:**
```powershell
# 1. 安装Python 3.8+
# 从 https://www.python.org/downloads/ 下载

# 2. 安装Ollama
# 从 https://ollama.com/download 下载

# 3. 安装Git
# 从 https://git-scm.com/download/win 下载

# 4. 配置环境变量
# 系统属性 -> 环境变量 -> 添加Python和Ollama到PATH

# 5. 安装依赖
pip install -r requirements.txt
```

#### Docker配置（可选）

**使用Docker运行Ollama:**
```bash
# 拉取Ollama Docker镜像
docker pull ollama/ollama

# 运行Ollama容器
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama

# 在容器中拉取模型
docker exec -it ollama ollama pull qwen2.5-coder:7b
docker exec -it ollama ollama pull nomic-embed-text:latest

# 配置环境变量指向Docker容器
export OLLAMA_BASE_URL=http://localhost:11434
```

### 常见前置条件问题解决

#### 问题1：Python版本冲突

**症状**：多个Python版本导致混乱

**解决方案**：
```bash
# 使用pyenv管理Python版本
brew install pyenv  # macOS
# 或
curl https://pyenv.run | bash  # Linux

# 安装特定Python版本
pyenv install 3.9.7
pyenv local 3.9.7

# 验证
python --version
```

#### 问题2：Ollama服务无法启动

**症状**：`ollama serve` 报错

**解决方案**：
```bash
# 检查端口占用
lsof -i :11434
# 如果端口被占用，杀掉进程
kill -9 <PID>

# 检查日志
cat ~/.ollama/logs/server.log

# 重置Ollama
rm -rf ~/.ollama
ollama serve
```

#### 问题3：模型下载很慢

**症状**：模型下载速度慢或失败

**解决方案**：
```bash
# 设置超时时间
export OLLAMA_REQUEST_TIMEOUT=600

# 使用代理
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080

# 限制并发下载
export OLLAMA_MAX_QUEUE=1
```

#### 问题4：依赖包安装失败

**症状**：`pip install -r requirements.txt` 失败，错误包括 "resolution-too-deep"

**原因**：不同包之间的依赖版本冲突，pip无法解决复杂的依赖关系。

**解决方案：**

**方案1：使用专用安装脚本（推荐）**
```bash
# Linux/macOS
./install_deps.sh

# Windows PowerShell
.\install_deps.ps1
```

这个脚本会：
- 升级pip和setuptools
- 分步骤安装依赖，避免冲突
- 先安装问题包（banks），再安装其他依赖
- 提供详细的安装验证

**方案2：手动分步安装**
```bash
# 先升级基础工具
python3 -m pip install --upgrade pip setuptools wheel

# 先安装banks（导致冲突的包）
python3 -m pip install banks==2.4.0

# 然后按顺序安装其他依赖
python3 -m pip install chromadb==0.4.24
python3 -m pip install pypdf==4.3.1
python3 -m pip install requests==2.32.3
python3 -m pip install python-dotenv==1.0.1
python3 -m pip install rich==13.9.4
python3 -m pip install prompt-toolkit==3.0.48

# 最后安装llama-index系列
python3 -m pip install llama-index==0.10.46
python3 -m pip install llama-index-embeddings-ollama==0.1.3
python3 -m pip install llama-index-llms-ollama==0.2.0
python3 -m pip install llama-index-readers-file==0.1.4
python3 -m pip install llama-index-vector-stores-chroma==0.1.8
```

**方案3：使用pip的额外参数**
```bash
# 禁用缓存
pip install -r requirements.txt --no-cache-dir

# 使用预编译包
pip install -r requirements.txt --prefer-binary

# 增加超时时间
pip install -r requirements.txt --timeout 1000
```

**方案4：使用新的虚拟环境**
```bash
# 删除旧的虚拟环境
rm -rf venv

# 创建新的虚拟环境
python3 -m venv venv
source venv/bin/activate

# 升级pip
python -m pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt
```

**方案5：降级llama-index版本**
```bash
# 如果最新版本有冲突，使用稳定版本
pip install llama-index==0.9.6
pip install llama-index-embeddings-ollama==0.1.2
pip install llama-index-llms-ollama==0.1.3
```

**验证安装成功**
```bash
python -c "import llama_index, chromadb, rich; print('所有依赖正常')"
```

#### 问题5：ChromaDB遥测错误

**症状**: 运行时出现以下错误：
```
Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument but 3 were given
Failed to send telemetry event ClientCreateCollectionEvent: capture() takes 1 positional argument but 3 were given
```

**原因**: ChromaDB的遥测功能与某些版本不兼容，导致`capture()`函数参数错误。

**解决方案**：

**方案1：使用修复后的代码（推荐）**
```bash
# 项目代码已经自动禁用ChromaDB遥测
# 确保使用最新版本的代码
git pull  # 如果是从git仓库获取的代码

# 验证修复
python query_interface.py --data ./data
```

**方案2：手动禁用遥测**
```bash
# 在运行前设置环境变量
export ANONYMIZED_TELEMETRY=False
export CHROMA_TELEMETRY=False

# 然后运行程序
python query_interface.py --data ./data
```

**方案3：降级ChromaDB版本**
```bash
# 降级到稳定的0.4.22版本
pip install chromadb==0.4.22

# 更新requirements.txt中的版本号
# chromadb==0.4.22
```

**方案4：在代码中禁用遥测**
```python
import os
import logging

# 在导入chromadb之前添加
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY'] = 'False'
logging.getLogger("chromadb").setLevel(logging.ERROR)

import chromadb
```

**注意**: 
- 这个错误不影响核心功能，知识库查询和代码生成都可以正常使用
- 只是影响用户体验，会显示错误信息
- 项目代码已经包含自动禁用遥测的配置
- 如仍遇到此错误，请确保使用最新版本的代码

#### 问题6：urllib3 OpenSSL警告（macOS）

**症状**: 在macOS上运行时出现以下警告：
```
NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+, currently the 'ssl' module is compiled with LibreSSL 2.8.3
```

**原因**: macOS系统使用LibreSSL而不是OpenSSL，urllib3 v2.x检测到LibreSSL版本兼容性警告。这是macOS系统的正常情况，不影响功能。

**解决方案**：

**方案1：使用修复后的代码（推荐）**
```bash
# 项目代码已自动禁用此警告
# 确保使用最新版本的代码
git pull

# 重新安装依赖以获取兼容版本
pip install -r requirements.txt
```

**方案2：手动降级urllib3**
```bash
# 降级到v1.x版本，与LibreSSL兼容
pip install "urllib3<2.0.0"
```

**方案3：根本解决方案（macOS）**
```bash
# 使用pyenv安装带有OpenSSL的Python版本
pyenv install 3.9.18
pyenv local 3.9.18

# 或使用Homebrew安装Python
brew install python@3.9
```

**方案4：代码中禁用警告**
```python
import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")
```

**注意**:
- 这个警告只在macOS上出现，不影响功能
- 项目代码已包含自动禁用警告的配置
- urllib3 v1.x版本在安全性上可能不如v2.x，但项目已自动降级以确保兼容性

### 前置条件验证清单

运行以下命令验证所有前置条件：

```bash
# 完整验证脚本
echo "=== 最终验证 ==="

# 1. Python版本
python3 --version && python3 -c "import sys; assert sys.version_info >= (3, 8)"

# 2. Ollama服务
curl -s http://localhost:11434/api/tags && echo "Ollama服务正常"

# 3. 模型可用
ollama run qwen2.5-coder:7b "test" && echo "主模型正常"
ollama run nomic-embed-text:latest "test" && echo "嵌入模型正常"

# 4. Python依赖
python3 -c "import llama_index, chromadb, rich; print('所有依赖正常')"

# 5. 运行项目测试
python3 -c "from query_interface import parse_command; print('项目导入正常')"

echo "=== 验证完成，可以开始使用 ==="
```

---

## 安装指南

### 步骤1：安装Ollama

**Linux/macOS:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
```powershell
# 从 https://ollama.com/download 下载安装包
# 或使用WSL2
wsl --install
curl -fsSL https://ollama.com/install.sh | sh
```

### 步骤2：拉取所需模型

```bash
# 主模型（代码生成 + 推理）
ollama pull qwen2.5-coder:7b

# 嵌入模型（语义编码）
ollama pull nomic-embed-text:latest

# 验证安装
ollama list
```

### 步骤3：克隆项目

```bash
git clone <repository-url>
cd ollama-qwen-coder-rag-lib
```

### 步骤4：创建Python虚拟环境（推荐）

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 升级pip
pip install --upgrade pip
```

### 步骤5：安装Python依赖

**推荐方法：使用专用安装脚本（避免依赖冲突）**
```bash
# Linux/macOS
./install_deps.sh

# Windows PowerShell
.\install_deps.ps1
```

**标准安装方法：**
```bash
cd ollama-qwen-coder-rag-lib
pip install -r requirements.txt
```

**如果遇到依赖冲突（如 "resolution-too-deep" 错误）：**
```bash
# 方案1：使用脚本自动解决（推荐）
./install_deps.sh      # Linux/macOS
.\install_deps.ps1     # Windows

# 方案2：手动分步安装
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install banks==2.4.0
python3 -m pip install chromadb==0.4.24
python3 -m pip install pypdf==4.3.1
# ... 其他依赖

# 方案3：使用备用依赖配置
pip install -r requirements_alternative.txt

# 方案4：使用pip的额外参数
pip install -r requirements.txt --no-cache-dir --prefer-binary
```

**依赖清单（当前版本）：**
- llama-index >= 0.10.0
- llama-index-embeddings-ollama >= 0.1.0
- llama-index-llms-ollama >= 0.1.0
- llama-index-readers-file >= 0.1.0
- llama-index-vector-stores-chroma >= 0.1.0
- chromadb >= 0.4.0
- pypdf >= 4.0.0
- requests >= 2.31.0
- python-dotenv >= 1.0.0
- rich >= 13.0.0
- prompt-toolkit >= 3.0.0

### 步骤6：验证安装

```bash
# 测试Ollama连接
ollama run qwen2.5-coder:7b "Hello, this is a test."

# 测试Python环境
python -c "import llama_index; import chromadb; print('Dependencies OK')"
```

---

## 配置说明

### 环境变量配置

创建 `.env` 文件（可选）：

```bash
# Ollama配置
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=qwen2.5-coder:7b
EMBED_MODEL=nomic-embed-text:latest

# RAG配置
CHUNK_SIZE=1024
CHUNK_OVERLAP=200
TOP_K=5
SIMILARITY_CUTOFF=0.7

# Agent配置
MAX_HISTORY=100
MAX_ITERATIONS=50
TIMEOUT=300
CODE_AGENT_AUTO_CONFIRM=false
```

### 配置文件说明

所有配置都在 `config.py` 中定义：

```python
# 路径配置
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"          # 文档存放目录
INDEX_DIR = BASE_DIR / "index_storage" # 索引存储目录

# 向量数据库配置
VECTOR_DB_PATH = str(INDEX_DIR / "chroma_db")

# 安全策略
READONLY_COMMANDS = ("ls", "pwd", "echo", "cat", ...) # 只读命令
DANGEROUS_PATTERNS = (r"rm -rf /", r"dd if=/dev/zero", ...) # 危险模式
```

---

## 快速开始

### 场景1：首次使用 - 知识库问答

```bash
# 1. 准备文档
mkdir -p data
cp ~/Documents/*.pdf data/
cp ~/notes/*.md data/

# 2. 启动带知识库的界面
python query_interface.py --data ./data

# 3. 首次会看到教程，按任意键继续
# 4. 开始查询
>>> /ask 这篇文章的主要观点是什么？
>>> /ask 解释一下提到的算法原理
>>> /stats
>>> /sources
```

### 场景2：代码任务 - 自动化开发

```bash
# 1. 启动Agent模式
python query_interface.py

# 2. 提交代码任务
>>> /agent 写一个Python的快速排序算法，保存到sort.py，然后创建测试文件验证

# 3. 观察执行过程
# 系统会自动：
# - 生成排序算法代码
# - 写入sort.py
# - 创建测试文件
# - 运行测试
# - 根据结果调整代码
# - 最终给出确认

# 4. 查看执行摘要
>>> /summary
```

### 场景3：单次查询

```bash
# 知识库单次查询
python query_interface.py --data ./papers --query "实验结果的准确率是多少？"

# Agent单次任务
python query_interface.py --agent "检查项目中的所有TODO注释"
```

---

## 实战场景示例

### 场景1：学术研究 - 论文综述

**目标**: 分析多篇论文，撰写文献综述

```bash
# 1. 准备论文文档
mkdir -p data/papers
cp ~/downloads/*.pdf data/papers/

# 2. 启动知识库模式
python query_interface.py --data ./data

# 3. 添加论文到知识库
>>> /add data/papers/paper1.pdf
>>> /add data/papers/paper2.pdf
>>> /add data/papers/paper3.pdf

# 4. 查询论文内容
>>> /ask paper1的主要贡献是什么？
>>> /ask paper2的方法论有什么特点？
>>> /ask 比较这三篇论文在实验设计上的差异
>>> /ask 总结这些论文中的关键技术趋势

# 5. 获取具体数据
>>> /ask paper1中提到的准确率是多少？
>>> /sources  # 查看数据来源
```

### 场景2：代码开发 - 新功能实现

**目标**: 为现有项目添加新功能并测试

```bash
# 1. 启动Agent模式
python query_interface.py

# 2. 分析现有项目
>>> /agent 分析当前项目结构，找出主要的模块和它们的职责

# 3. 添加新功能
>>> /agent 在user模块中添加一个send_email函数，使用SMTP发送邮件，包含错误处理

# 4. 创建测试
>>> /agent 为send_email函数创建单元测试，包括成功和失败场景

# 5. 运行测试
>>> /exec python -m pytest tests/test_user.py -v

# 6. 根据结果修改
>>> /agent 根据测试结果修复send_email函数中的问题

# 7. 代码审查
>>> /agent 检查send_email函数的代码质量，提供改进建议
```

### 场景3：项目重构 - 代码优化

**目标**: 重构旧代码，提高可维护性

```bash
# 1. 启动Agent模式
python query_interface.py

# 2. 分析代码问题
>>> /agent 分析legacy.py文件，找出代码异味和可改进之处

# 3. 重构第一步
>>> /agent 将legacy.py中的重复代码提取为公共函数

# 4. 重构第二步
>>> /agent 改进legacy.py中的错误处理，添加日志记录

# 5. 重构第三步
>>> /agent 优化legacy.py的性能，减少不必要的计算

# 6. 验证重构
>>> /agent 为重构后的代码生成测试用例
>>> /exec python -m pytest tests/test_legacy.py

# 7. 对比分析
>>> /file legacy.py  # 查看重构前的代码
>>> /file legacy_refactored.py  # 查看重构后的代码
```

### 场景4：文档生成 - API文档

**目标**: 为API接口生成详细文档

```bash
# 1. 启动带知识库的模式
python query_interface.py --data ./docs

# 2. 添加现有文档
>>> /add docs/api_spec.md
>>> /add docs/architecture.md

# 3. 生成新文档
>>> /agent 基于api.py文件生成API文档，保存到docs/api_new.md

# 4. 完善文档
>>> /ask 在api_new.md中添加代码示例和错误码说明
>>> /ask 生成API使用最佳实践指南

# 5. 格式化文档
>>> /agent 将文档转换为Markdown格式，添加目录和链接
```

### 场景5：数据分析 - 日志分析

**目标**: 分析服务器日志，找出问题和趋势

```bash
# 1. 准备日志文件
cp /var/log/app/*.log data/

# 2. 启动Agent模式
python query_interface.py

# 3. 分析日志
>>> /agent 分析error.log，找出最常见的错误类型
>>> /agent 统计access.log中的访问频率和高峰时段

# 4. 生成报告
>>> /agent 生成日志分析报告，保存到logs/report.md

# 5. 创建监控脚本
>>> /agent 编写日志监控脚本，当错误率超过阈值时发送警报
```

### 场景6：故障排查 - Bug定位

**目标**: 定位并修复生产环境bug

```bash
# 1. 启动Agent模式
python query_interface.py

# 2. 分析错误信息
>>> /agent 分析以下错误日志，找出可能的原因：[粘贴错误日志]

# 3. 搜索相关代码
>>> /search "NullPointer" --max-results 20
>>> /search "database connection" --max-results 10

# 4. 定位问题
>>> /file src/database.py:100-150

# 5. 修复bug
>>> /agent 修复database.py中的连接泄漏问题

# 6. 验证修复
>>> /agent 为修复编写测试用例
>>> /exec python -m pytest tests/test_database.py
```

### 场景7：配置迁移 - 系统升级

**目标**: 将配置从旧版本迁移到新版本

```bash
# 1. 启动Agent模式
python query_interface.py

# 2. 分析配置差异
>>> /file config_old.yml
>>> /file config_new_template.yml
>>> /agent 对比两个配置文件的差异，生成迁移指南

# 3. 自动迁移
>>> /agent 根据config_old.yml生成config_new.yml，转换格式并添加新字段

# 4. 验证配置
>>> /agent 验证config_new.yml的格式和完整性

# 5. 生成迁移脚本
>>> /agent 编写配置迁移脚本，支持批量转换
```

### 场景8：学习教程 - 技能提升

**目标**: 学习新技术并练习

```bash
# 1. 准备学习资料
mkdir -p data/learning
cp ~/tutorials/*.md data/learning/
cp ~/docs/*.pdf data/learning/

# 2. 启动知识库模式
python query_interface.py --data ./learning

# 3. 学习基础概念
>>> /ask 什么是Docker，它解决了什么问题？
>>> /ask 解释Kubernetes的核心概念

# 4. 实践练习
>>> /agent 根据教程创建一个Docker Compose文件
>>> /agent 编写Kubernetes的Deployment配置

# 5. 检查学习效果
>>> /agent 生成10道关于Docker的练习题，并提供答案

# 6. 深入理解
>>> /ask 对比Docker和虚拟机的优缺点
>>> /sources  # 查看知识来源
```

### 场景9：团队协作 - 代码审查

**目标**: 协助团队进行代码审查

```bash
# 1. 启动Agent模式
python query_interface.py

# 2. 审查PR代码
>>> /agent 审查src/pr_feature分支的代码，重点关注安全性和性能

# 3. 生成审查报告
>>> /agent 生成代码审查报告，包括问题和改进建议

# 4. 提供修复建议
>>> /agent 针对审查发现的问题，提供具体的修复方案

# 5. 生成最佳实践
>>> /agent 基于本次审查，总结该项目的代码规范和最佳实践
```

### 场景10：自动化运维 - 部署脚本

**目标**: 生成自动化部署和运维脚本

```bash
# 1. 启动Agent模式
python query_interface.py

# 2. 生成部署脚本
>>> /agent 编写应用部署脚本，包括环境检查、依赖安装、服务启动

# 3. 生成监控脚本
>>> /agent 编写服务监控脚本，检查进程状态、日志、性能指标

# 4. 生成备份脚本
>>> /agent 编写数据备份脚本，支持定期备份和恢复

# 5. 生成CI/CD配置
>>> /agent 生成GitHub Actions配置文件，实现自动化测试和部署
```

---

## 详细功能说明

### 1. RAG知识库功能

#### 支持的文档格式

- **文档类**: PDF, Markdown (.md, .markdown), TXT
- **代码类**: Python, JavaScript, TypeScript, Java, C/C++, Go, Rust
- **数据类**: JSON, YAML, XML, HTML

#### 知识库构建

```python
from rag_engine import build_knowledge_base, RAGEngine

# 方式1：一键构建
engine = build_knowledge_base("./data")

# 方式2：手动构建
from rag_engine import RAGEngine
from document_loader import load_documents

engine = RAGEngine()
docs = load_documents("./data")
engine.add_documents(docs)
engine.build_index()
engine.load_index()
```

#### 查询方式

```python
# 基础查询
answer = engine.query("什么是注意力机制？")
print(answer)

# 带来源的查询
result = engine.query_with_sources("RAG的优势是什么？")
print(f"答案: {result['answer']}")
for src in result['sources']:
    print(f"来源: {src['file']} (相似度: {src['score']:.3f})")
```

#### CLI命令

```bash
/ask <问题>              # 直接查询知识库
/add <文件路径>          # 添加文档到知识库
/stats                   # 显示知识库统计信息
/sources                 # 显示上次查询的来源
/clear                   # 清空知识库索引
```

### 2. ReAct Agent功能

#### 工作原理

ReAct（Reasoning + Acting）通过以下循环执行任务：

```
Thought: 思考当前状态和下一步行动
  ↓
Action: 选择并执行工具
  ↓
Observation: 观察执行结果
  ↓
Thought: 基于结果继续思考...
```

#### 可用工具

| 工具名 | 功能 | 安全等级 | 使用场景 |
|--------|------|----------|----------|
| read_file | 读取文件 | 安全 | 查看代码、配置文件 |
| write_file | 写入文件 | 需确认 | 生成代码、修改配置 |
| execute_command | 执行命令 | 需确认 | 运行测试、git操作 |
| list_directory | 列出目录 | 安全 | 浏览项目结构 |
| search_files | 搜索文件 | 安全 | 查找代码片段 |
| query_knowledge_base | 查询知识库 | 安全 | 结合文档信息 |

#### CLI命令

```bash
/agent <任务描述>        # 进入Agent自动执行模式
/file <文件路径>          # 快速读取文件
/write <文件路径>         # 交互式写入文件
/exec <命令>             # 执行shell命令
/search <关键词>          # 搜索文件内容
/history                 # 查看对话历史
/summary                 # 查看执行步骤摘要
/reset                   # 重置对话上下文
```

### 3. 文件操作工具

#### 读取文件

```bash
# CLI方式
>>> /file main.py
>>> /file README.md

# 显示行数范围
>>> /file main.py:20-30

# 代码语法高亮（支持的语言）
>>> /file script.py      # Python语法高亮
>>> /file config.json    # JSON格式化显示
```

#### 写入文件

```bash
# CLI方式
>>> /write test.py
# 系统会提示输入内容，Ctrl+D结束

# Agent方式（推荐）
>>> /agent 创建一个Python类的定义，保存到person.py
```

#### 搜索功能

```bash
# 搜索文件内容
>>> /search "def hello"
>>> /search "TODO"
>>> /search "API_KEY"

# 搜索多个文件
>>> /search "class User" --max-results 10
```

---

## 高级用法

### 1. 自定义模型配置

```bash
# 使用不同的Ollama模型
python query_interface.py --model qwen2.5-coder:14b

# 指定远程Ollama服务
python query_interface.py --host http://192.168.1.100:11434
```

### 2. 批量文档处理

```bash
# 只构建索引，不进入交互模式
python query_interface.py --data ./papers --build-only

# 指定文件类型
python query_interface.py --data ./docs --types .pdf,.md

# 清空现有索引重新构建
python query_interface.py --data ./docs --clear
```

### 3. 自动化脚本集成

```bash
# 自动确认模式（用于脚本，危险！）
python query_interface.py --yes --agent "运行所有测试"

# 不使用历史记录
python query_interface.py --no-history --agent "清理临时文件"
```

### 4. 编程接口使用

```python
#!/usr/bin/env python3
from query_interface import parse_command, classify_mode

# 命令解析
cmd = parse_command("/ask 什么是机器学习？")
print(f"类型: {cmd.cmd_type}")
print(f"参数: {cmd.arg}")

# 模式分类
mode = classify_mode(cmd.cmd_type, has_rag_engine=True)
print(f"推荐模式: {mode}")
```

### 5. 调试和日志

```bash
# 查看详细日志
python query_interface.py --data ./docs --verbose

# 保存会话历史
# 会话自动保存到 ~/.code_agent_history.json
# 可以查看和恢复之前的对话
```

---

## 知识库智能优化

系统新增了知识库智能优化功能，可以自动将知识库文档转化为可重用的Skills，并提供快照管理功能。

### 1. 自动快照系统

#### 功能特性
- **自动快照**: 每次添加文档时自动创建知识库快照
- **版本管理**: 保留最近10个快照，自动清理旧版本
- **快照恢复**: 支持一键恢复到任意历史快照
- **迁移支持**: 自动生成恢复脚本，便于知识库迁移

#### 使用方法

```bash
# 查看所有快照
>>> /snapshot-list

输出示例：
┌─────────────────────────────────────────────────────────────┐
│ 📚 知识库快照列表                                              │
├─────────────────────────────────────────────────────────────┤
│ snapshot_001 - 2024-01-15 14:30:22 (触发: 手动)              │
│   文档数: 5, 总chunks: 120                                    │
├─────────────────────────────────────────────────────────────┤
│ snapshot_002 - 2024-01-15 15:45:10 (触发: 自动)              │
│   文档数: 7, 总chunks: 156                                    │
└─────────────────────────────────────────────────────────────┘

# 手动创建快照
>>> /snapshot-create

# 恢复指定快照
>>> /snapshot-restore snapshot_002
```

#### 配置选项

```python
# 在RAGEngine中启用/禁用自动快照
engine = RAGEngine(enable_auto_snapshot=True)  # 默认启用

# 配置快照管理器
from knowledge_snapshot import KnowledgeSnapshotManager

manager = KnowledgeSnapshotManager(
    index_dir="./index_storage",
    snapshot_dir="./.devin/knowledge/snapshots",
    max_snapshots=10  # 默认保留10个快照
)
```

### 2. 知识库到Skill智能转化

#### 功能特性
- **智能分类**: 自动区分通用型vs项目型文档
- **主题合并**: 按主题合并多个文档生成统一skill
- **多平台支持**: 同时支持Devin和OpenCode平台
- **自动路径管理**: 通用型skill放入全局目录，项目专用型放入项目目录

#### 使用方法

```bash
# 将知识库转化为Skills
>>> /generate-skills

输出示例：
🔄 正在分析知识库...
📊 发现 8 个文档，提取 3 个主题
✅ 生成 3 个Skills:
   - cloudflare-networking-skill (全局)
   - linux-commands-skill (全局)  
   - project-config-skill (项目)

# 查看知识库文档摘要
>>> /knowledge-summary

输出示例：
┌─────────────────────────────────────────────────────────────┐
│ 📚 知识库文档摘要                                             │
├─────────────────────────────────────────────────────────────┤
│ 总文档数: 8                                                   │
│ 总chunks数: 234                                               │
│ 主题分布:                                                     │
│   - Cloudflare (3文档)                                       │
│   - Linux命令 (2文档)                                        │
│   - 项目配置 (3文档)                                         │
└─────────────────────────────────────────────────────────────┘
```

#### 配置选项

```python
from knowledge_to_skills import KnowledgeToSkillsEngine

# 创建转化引擎（可禁用安全扫描）
engine = KnowledgeToSkillsEngine(
    index_dir="./index_storage",
    enable_security=False  # 可选禁用安全扫描
)

# 执行转化
results = engine.convert(output_dir="./.devin/skills")
```

#### Skill输出目录

系统会自动根据文档类型选择输出目录：
- **通用型文档**: `~/.config/devin/skills/` (全局skills)
- **项目专用型**: `.devin/skills/` (项目特定skills)

### 3. 内容安全防护 ⚡

系统内置了**内容安全扫描器**，防止基于文档的提示词攻击。

#### 安全检测能力

- **提示词注入检测**: 检测 "ignore instructions"、"bypass security" 等攻击模式
- **角色劫持防护**: 防止恶意改变AI角色和行为
- **高风险关键词**: 识别危险操作词汇（delete, destroy, exploit等）
- **可疑模式检测**: 检测字符重复、Base64编码等混淆攻击
- **威胁等级评估**: 5级威胁分类（SAFE/LOW/MEDIUM/HIGH/CRITICAL）

#### 安全策略

```python
# 启用安全扫描（默认启用）
engine = RAGEngine(enable_security=True)

# 禁用安全扫描（不推荐）
engine = RAGEngine(enable_security=False)
```

#### 威胁等级处理

- **HIGH（严重威胁）**: 拒绝添加文档到知识库，拒绝生成skill
- **MEDIUM（中等威胁）**: 允许添加但发出警告，净化内容后生成skill
- **LOW（轻微威胁）**: 正常处理，记录信息日志

#### 使用示例

```python
from content_security import ContentSecurityScanner, SkillSecurityFilter

# 创建扫描器
scanner = ContentSecurityScanner()

# 扫描内容
content = "这是一个关于Cloudflare配置的技术文档"
is_safe, issues = scanner.scan_content(content, filename="document.md")

if is_safe:
    print("内容安全")
else:
    print(f"检测到 {len(issues)} 个安全问题")
    for issue in issues:
        print(f"- {issue.issue_type}: {issue.description}")

# 评估威胁等级
threat_level = scanner.assess_overall_threat(issues)
print(f"威胁等级: {threat_level.value}")
```

### 4. 命令行工具使用

#### 知识库转化引擎

```bash
# 独立运行转化引擎
python knowledge_to_skills.py --summary

# 查看帮助
python knowledge_to_skills.py --help
```

#### 快照管理工具

```bash
# 列出所有快照
python knowledge_snapshot.py --action list

# 创建新快照
python knowledge_snapshot.py --action create

# 查看最新快照
python knowledge_snapshot.py --action latest

# 恢复指定快照
python knowledge_snapshot.py --action restore --snapshot-id <id>

# 删除指定快照
python knowledge_snapshot.py --action delete --snapshot-id <id>
```

### 5. 详细文档

- **[知识库优化实现总结](docs/KNOWLEDGE_OPTIMIZATION_SUMMARY.md)** - 完整的实现说明和设计细节
- **[安全功能文档](docs/SECURITY_DOCUMENTATION.md)** - 内容安全扫描器的详细使用指南

---

## 安全机制

### 多层安全防护

#### 1. 命令安全检查

```python
# 自动检测危险命令
危险模式示例:
- rm -rf /
- dd if=/dev/zero
- chmod 777 /
- curl ... | sh

# 风险等级分类:
- critical: 立即拒绝，不执行
- high: 需要用户确认
- medium: 需要用户确认
- low: 可以直接执行（只读命令）
```

#### 2. 用户确认机制

```bash
# 对于高风险操作，系统会要求确认
即将执行命令: rm file.txt
风险等级: medium
是否确认执行? (y/n): y

# Agent工具也需要确认
即将执行 write_file: {"path": "config.py", "content": "..."}
是否确认? (y/n): n
[用户拒绝] write_file 未执行
```

#### 3. 工具安全等级

| 安全等级 | 工具示例 | 行为 |
|----------|----------|------|
| 安全 | read_file, list_directory | 直接执行，无需确认 |
| 需确认 | write_file, execute_command | 需要用户确认 |
| 危险 | rm -rf / | 拒绝执行 |

### 安全配置

```python
# 在config.py中配置
AUTO_CONFIRM = False  # 是否自动确认（仅用于自动化脚本）

# 自定义安全策略
READONLY_COMMANDS = ("ls", "pwd", "cat", ...)  # 扩展只读命令
DANGEROUS_PATTERNS = (r"rm -rf /", ...)      # 扩展危险模式
```

#### 4. 内容安全防护（防止提示词攻击）

系统新增了内容安全扫描器，自动扫描添加到知识库的文档，防止基于文档的提示词攻击。

**检测能力**：
- 提示词注入检测（"ignore instructions"、"bypass security"）
- 角色劫持防护（"You are now a hacker"）
- 高风险关键词识别（delete, destroy, exploit）
- 可疑模式检测（字符重复、Base64编码）

**配置选项**：
```python
# 启用/禁用安全扫描
engine = RAGEngine(enable_security=True)  # 默认启用

# 在Skill生成中启用/禁用安全扫描
engine = KnowledgeToSkillsEngine(
    index_dir="./index_storage",
    enable_security=True
)
```

**威胁等级**：
- **SAFE**: 无安全威胁
- **LOW**: 轻微风险（如高风险关键词）
- **MEDIUM**: 中等威胁（如角色定义）
- **HIGH**: 严重威胁（如提示词注入）
- **CRITICAL**: 极端威胁

详细说明请查看：[安全功能文档](docs/SECURITY_DOCUMENTATION.md)

---

## 故障排除

### 依赖冲突问题 (resolution-too-deep)

这是目前最常见的安装问题，以下按优先级排列的解决方案：

#### 🔥 方案1：使用专用安装脚本（强烈推荐）

```bash
./install_deps.sh      # Linux/macOS
.\install_deps.ps1     # Windows PowerShell
```

#### 🔧 方案2：使用备用依赖配置

```bash
pip install -r requirements_alternative.txt
```

#### 🛠️ 方案3：手动分步安装

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install banks==2.4.0
python3 -m pip install chromadb==0.4.24
python3 -m pip install pypdf==4.3.1
python3 -m pip install requests==2.32.3
python3 -m pip install python-dotenv==1.0.1
python3 -m pip install rich==13.9.4
python3 -m pip install prompt-toolkit==3.0.48
python3 -m pip install llama-index==0.10.46
python3 -m pip install llama-index-embeddings-ollama==0.1.3
python3 -m pip install llama-index-llms-ollama==0.2.0
python3 -m pip install llama-index-readers-file==0.1.4
python3 -m pip install llama-index-vector-stores-chroma==0.1.8
```

#### 🧹 方案4：清理环境重新安装

```bash
pip cache purge
python3 -m venv venv_clean
source venv_clean/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt --no-cache-dir --prefer-binary
```

#### 🔄 方案5：降级到稳定版本

```bash
pip install llama-index==0.9.6
pip install llama-index-embeddings-ollama==0.1.2
pip install llama-index-llms-ollama==0.1.3
pip install llama-index-readers-file==0.1.2
pip install llama-index-vector-stores-chroma==0.1.1
```

### 常见问题

#### 1. Ollama连接失败

**症状**: `[错误] 连接Ollama失败`

**解决方案**:
```bash
# 检查Ollama服务状态
ollama list

# 重启Ollama
# Linux: systemctl restart ollama
# macOS: brew services restart ollama

# 检查端口占用
lsof -i :11434

# 手动指定地址
export OLLAMA_BASE_URL=http://localhost:11434
```

#### 2. 模型下载缓慢

**解决方案**:
```bash
# 使用镜像加速（如果有）
export OLLAMA_HOST=https://registry.ollama.com

# 分批下载模型
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text:latest
```

#### 3. 内存不足

**症状**: 程序崩溃或响应缓慢

**解决方案**:
```bash
# 减少chunk大小
export CHUNK_SIZE=512

# 减少历史记录
export MAX_HISTORY=50

# 使用较小的模型
ollama pull qwen2.5-coder:3b
python query_interface.py --model qwen2.5-coder:3b
```

#### 4. 索引构建失败

**症状**: 文档加载或索引构建错误

**解决方案**:
```bash
# 检查文档格式
file data/*.pdf

# 清空索引重新构建
python query_interface.py --data ./data --clear

# 检查依赖
pip install --upgrade llama-index chromadb
```

#### 5. Python依赖冲突

**解决方案**:
```bash
# 创建干净的虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 调试技巧

```bash
# 启用详细日志
export DEBUG=1
python query_interface.py --data ./data

# 检查日志文件
ls -la ~/.code_agent_history.json

# 测试单个模块
python -m pytest tests/ -v

# 测试特定功能
python -c "from rag_engine import RAGEngine; print('RAG OK')"
python -c "from react_engine import ReActEngine; print('ReAct OK')"
```

---

## 最佳实践

### 1. 知识库管理

**文档组织建议**:
```
data/
├── papers/          # 学术论文
├── docs/            # 技术文档
├── notes/           # 学习笔记
├── code/            # 代码文件
└── config/          # 配置文件
```

**定期维护**:
```bash
# 定期重建索引
python query_interface.py --data ./data --clear

# 添加新文档时使用/add而非重新构建
>>> /add ./new_paper.pdf
```

### 2. Agent任务设计

**任务描述最佳实践**:

❌ **不好的描述**:
```
>>> /agent 修复代码
```

✅ **好的描述**:
```
>>> /agent 检查src/main.py中的所有TODO注释，分析每个TODO的优先级，给出实现建议
```

**复杂任务分解**:
```bash
# 将大任务分解为小步骤
>>> /agent 第一步：分析项目结构
>>> /agent 第二步：查找性能瓶颈
>>> /agent 第三步：提出优化方案
```

### 3. 安全使用

**生产环境建议**:
```bash
# 不要使用自动确认模式
# 避免在生产环境执行write_file操作
# 定期备份重要文件
# 使用Git版本控制

# 安全配置
export CODE_AGENT_AUTO_CONFIRM=false
export MAX_ITERATIONS=10  # 限制迭代次数
```

### 4. 性能优化

**提高响应速度**:
```bash
# 使用更快的模型
python query_interface.py --model qwen2.5-coder:3b

# 减少检索结果
export TOP_K=3

# 增加相似度阈值
export SIMILARITY_CUTOFF=0.8
```

**内存优化**:
```bash
# 减少chunk大小
export CHUNK_SIZE=512

# 限制历史记录
export MAX_HISTORY=30
```

### 5. 集成到工作流

**与Git结合**:
```bash
# 代码审查
>>> /agent 检查当前分支的所有修改，给出代码审查意见

# 自动化测试
>>> /agent 运行所有单元测试，汇总失败用例
```

**与文档结合**:
```bash
# 技术文档生成
>>> /agent 根据代码生成API文档，保存到docs/api.md

# README生成
>>> /agent 为项目生成README.md
```

---

## 进阶技巧

### 1. 自定义工具扩展

```python
from agent_tools import registry

# 注册自定义工具
def custom_tool(param: str) -> str:
    """自定义工具描述"""
    return f"处理结果: {param}"

registry.register(
    name="custom_tool",
    func=custom_tool,
    description="自定义工具的功能说明",
    params={"param": "参数说明"},
    safe=True  # 或False表示需要确认
)
```

### 2. 批量操作脚本

```bash
#!/bin/bash
# batch_process.sh

for file in data/*.pdf; do
    echo "Processing $file..."
    python query_interface.py \
        --data ./data \
        --query "总结 $(basename $file) 的核心内容" \
        >> summaries.txt
done
```

### 3. 多模型切换

```python
# 根据任务复杂度选择模型
simple_task = "总结这段文字"
complex_task = "实现一个复杂的算法"

if len(complex_task) > 50:
    model = "qwen2.5-coder:14b"  # 复杂任务用大模型
else:
    model = "qwen2.5-coder:7b"   # 简单任务用小模型
```

### 4. 知识库联邦

```python
# 管理多个知识库
engine1 = build_knowledge_base("./papers")
engine2 = build_knowledge_base("./docs")

# 联合查询
def federated_query(question):
    result1 = engine1.query(question)
    result2 = engine2.query(question)
    return merge_results(result1, result2)
```

---

## 社区和支持

### 获取帮助

- **文档**: 查看README.md和本TUTORIAL.md
- **示例**: 运行example.py查看基本用法
- **测试**: 运行pytest查看测试用例

### 贡献指南

欢迎贡献代码、报告问题或提出建议！

### 更新日志

- **v3.0**: 融合RAG和ReAct，统一CLI界面
- **v2.0**: 添加安全机制和工具链
- **v1.0**: 基础RAG功能

---

## 总结

这个智能文档+代码助手为开发者提供了一个强大的AI工具，既可以基于知识库进行智能问答，也可以通过ReAct Agent自动执行复杂的代码任务。

**核心优势**:
- 🚀 统一界面，双模式切换
- 🛡️ 多层安全保护
- 📚 丰富的文档支持
- 🤖 智能代码生成
- 🔧 灵活的配置选项

**适用场景**:
- 学术研究和论文分析
- 代码开发和项目维护
- 文档生成和知识管理
- 自动化测试和调试

开始使用吧！如有问题，请参考故障排除部分或查看更多文档。