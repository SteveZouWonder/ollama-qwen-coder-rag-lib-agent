# 安装和配置指南

> 本指南详细说明如何安装和配置智能文档+代码助手项目。

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
# 运行安装程序
```

### 步骤2：拉取所需模型

```bash
# 下载主模型（约4-5GB）
ollama pull qwen2.5-coder:7b

# 下载嵌入模型（约200MB）
ollama pull nomic-embed-text:latest
```

### 步骤3：克隆项目

```bash
git clone <项目地址>
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

**推荐方法：使用专用安装脚本**
```bash
./install_deps.sh      # Linux/macOS
.\install_deps.ps1     # Windows PowerShell
```

**标准方法：**
```bash
pip install -r requirements.txt
```

**如果遇到依赖冲突：**
```bash
# 使用备用配置
pip install -r requirements_alternative.txt
```

### 步骤5.5：安装OCR功能依赖（可选）

如果需要使用 OCR 图像识别功能，请安装以下依赖：

```bash
# OCR 核心依赖
pip install paddlepaddle==2.5.2
pip install paddleocr==2.7.0.3
pip install pytesseract==0.3.10
pip install pymupdf==1.23.8
pip install opencv-python==4.8.1.78
pip install pillow==10.1.0

# 安装 Tesseract（系统级）
# macOS
brew install tesseract tesseract-lang

# Linux (Ubuntu/Debian)
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra

# Windows
# 下载安装程序：https://github.com/UB-Mannheim/tesseract/wiki
```

> **注意**: OCR 功能是可选的，如果不安装这些依赖，系统会自动禁用 OCR 相关功能，不影响其他功能的使用。

### 步骤6：验证安装

```bash
# 检查Python依赖
pip list

# 检查Ollama服务
ollama list

# 测试模型
echo "测试" | ollama run qwen2.5-coder:7b "请回答：1+1等于几？"
```

---

## 配置说明

### 环境变量配置

**创建 .env 文件：**
```bash
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

chmod 600 .env
```

### 配置文件说明

**config.py**: 主配置文件，包含：
- Ollama连接配置
- 模型配置
- RAG参数
- Agent参数
- 安全配置

**桌面应用配置**: `config/app_config.json`
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

---

## 快速开始

### 场景1：首次使用 - 知识库问答

```bash
# 准备文档
mkdir data
cp 你的文档.pdf data/

# 启动带知识库的助手
python query_interface.py --data ./data

# 在交互界面中
>>> /ask 这篇文档的主要内容是什么？
>>> /stats
>>> /sources
```

### 场景2：代码任务 - 自动化开发

```bash
# 启动纯Agent模式
python query_interface.py

# 在交互界面中
>>> /agent 写一个Python快速排序，保存到sort.py
>>> /agent 测试sort.py是否工作正常
```

### 场景3：单次查询

```bash
# 知识库单次查询
python query_interface.py --data ./papers --query "实验结果是什么？"

# Agent单次任务
python query_interface.py --agent "检查main.py的语法错误"
```

---

## 常见配置问题

### 依赖冲突问题

**症状**: `pip install -r requirements.txt` 报错 "resolution-too-deep"

**解决方案**:
1. 使用专用安装脚本: `./install_deps.sh`
2. 使用备用依赖配置: `pip install -r requirements_alternative.txt`
3. 清理环境重新安装

### ChromaDB遥测错误

**症状**: ChromaDB遥测相关警告

**解决方案**:
```bash
# 项目已自动禁用遥测，如仍遇到错误：
export ANONYMIZED_TELEMETRY=False
```

### Ollama连接问题

**症状**: 无法连接到Ollama服务

**解决方案**:
1. 检查Ollama服务状态: `ps aux | grep ollama`
2. 检查端口: `lsof -i :11434`
3. 重启Ollama: `ollama serve`

---

**上一篇**: [项目概述和系统要求](01-overview.md) | **下一篇**: [实战场景示例](03-scenarios.md)