# 故障排除指南

> 本文档提供常见问题的解决方案和调试技巧。

---

## 依赖冲突问题 (resolution-too-deep)

### 🔥 方案1：使用专用安装脚本（强烈推荐）

```bash
# Linux/macOS
./install_deps.sh

# Windows PowerShell
.\install_deps.ps1
```

### 🔧 方案2：使用备用依赖配置

```bash
pip install -r requirements_alternative.txt
```

### 🛠️ 方案3：手动分步安装

```bash
# 安装核心依赖
pip install llama-index>=0.10.0
pip install chromadb>=0.4.0

# 安装Ollama集成
pip install llama-index-embeddings-ollama>=0.1.0
pip install llama-index-llms-ollama>=0.1.0

# 安装文档读取器
pip install llama-index-readers-file>=0.1.0
pip install pypdf>=4.0.0

# 安装其他依赖
pip install requests>=2.31.0
pip install python-dotenv>=1.0.0
pip install rich>=13.0.0
pip install prompt-toolkit>=3.0.0
```

### 🧹 方案4：清理环境重新安装

```bash
# 删除虚拟环境
rm -rf venv

# 重新创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 重新安装
pip install --upgrade pip
pip install -r requirements.txt
```

### 🔄 方案5：降级到稳定版本

```bash
# 使用更保守的版本要求
pip install "llama-index<0.11.0"
pip install "chromadb<0.5.0"
```

---

## 常见问题

### 1. Ollama连接失败

**症状**:
```
ConnectionError: Failed to connect to Ollama service
```

**解决方案**:

1. 检查Ollama服务是否运行:
```bash
ps aux | grep ollama
lsof -i :11434
```

2. 启动Ollama服务:
```bash
ollama serve
# 或后台运行
nohup ollama serve > ollama.log 2>&1 &
```

3. 检查防火墙设置:
```bash
# Linux (ufw)
sudo ufw allow 11434/tcp

# Linux (firewalld)
sudo firewall-cmd --permanent --add-port=11434/tcp
sudo firewall-cmd --reload
```

4. 验证连接:
```bash
curl http://localhost:11434/api/tags
```

### 2. 模型下载缓慢

**症状**: 模型下载速度很慢或失败

**解决方案**:

1. 使用代理:
```bash
export HTTPS_PROXY=http://your-proxy:port
export HTTP_PROXY=http://your-proxy:port
ollama pull qwen2.5-coder:7b
```

2. 使用国内镜像（如果有）

3. 分批下载小模型:
```bash
# 先下载小的嵌入模型
ollama pull nomic-embed-text:latest
# 再下载大的主模型
ollama pull qwen2.5-coder:7b
```

4. 检查网络连接:
```bash
ping ollama.com
curl -I https://ollama.com
```

### 3. 内存不足

**症状**: 程序运行缓慢或崩溃

**解决方案**:

1. 检查内存使用:
```bash
free -h  # Linux
vm_stat  # macOS
```

2. 调整模型大小:
```bash
# 使用更小的模型
ollama pull qwen2.5-coder:3b
```

3. 减少并发数:
```python
# 在配置中调整
MAX_ITERATIONS = 30  # 降低迭代次数
```

4. 清理不必要的进程:
```bash
# 关闭其他占用内存的程序
```

### 4. 索引构建失败

**症状**: 知识库索引构建失败

**解决方案**:

1. 检查文档格式:
```bash
# 确保文档格式正确
file data/*.pdf
```

2. 减少文档数量:
```bash
# 分批处理文档
python query_interface.py --data ./data1
python query_interface.py --data ./data2
```

3. 检查磁盘空间:
```bash
df -h
# 确保有足够空间存储索引
```

4. 使用更小的分块:
```python
# 在配置中调整
CHUNK_SIZE = 512
CHUNK_OVERLAP = 100
```

### 5. Python依赖冲突

**症状**: ImportError 或版本冲突错误

**解决方案**:

1. 使用虚拟环境:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. 检查已安装的包:
```bash
pip list
pip check
```

3. 升级pip:
```bash
pip install --upgrade pip
```

4. 使用国内镜像:
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## ChromaDB相关问题

### ChromaDB遥测错误

**症状**: ChromaDB遥测相关警告

**解决方案**:
```bash
# 项目已自动禁用遥测，如仍遇到错误：
export ANONYMIZED_TELEMETRY=False
export DO_NOT_TRACK=1
```

### ChromaDB连接失败

**症状**: 无法连接到ChromaDB

**解决方案**:
```bash
# 清理ChromaDB缓存
rm -rf index_storage/chroma_db

# 重新构建索引
python query_interface.py --data ./data
```

---

## urllib3 OpenSSL警告（macOS）

### 问题描述

**症状**:
```
NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+, currently the 'ssl' module is compiled with 'LibreSSL 2.8.3'
```

### 解决方案

这是macOS系统的兼容性警告，不影响功能使用：

1. **忽略警告**: 可以安全忽略，不影响功能

2. **降级urllib3**:
```bash
pip install "urllib3<2.0.0"
```

3. **升级Python**: 使用Python 3.10+的新版本

---

## 调试技巧

### 1. 启用详细日志

```bash
# 设置环境变量
export DEBUG=1
export LOG_LEVEL=DEBUG

# 运行程序
python query_interface.py --data ./data
```

### 2. 检查配置

```bash
# 显示当前配置
python -c "
from config import Config
config = Config()
print(config.__dict__)
"
```

### 3. 测试Ollama连接

```bash
# 测试基本连接
curl http://localhost:11434/api/tags

# 测试模型
echo "测试" | ollama run qwen2.5-coder:7b "请回答：1+1等于几？"
```

### 4. 验证依赖安装

```bash
# 检查关键依赖
python -c "import llama_index; print('LlamaIndex OK')"
python -c "import chromadb; print('ChromaDB OK')"
python -c "import requests; print('Requests OK')"
```

### 5. 清理缓存

```bash
# 清理Python缓存
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete

# 清理索引缓存
rm -rf index_storage/*
```

---

## 获取帮助

如果以上解决方案无法解决问题：

1. **查看日志**:
```bash
# 查看应用日志
cat logs/app.log

# 查看错误日志
cat logs/*.log | grep ERROR
```

2. **运行诊断脚本**:
```bash
./check_prereqs.sh
```

3. **检查文档**:
- README.md
- 技术文档
- GitHub Issues

4. **提供信息**:
在寻求帮助时，请提供：
- 操作系统版本
- Python版本
- 错误信息
- 配置文件
- 日志文件

---

**上一篇**: [桌面应用](05-desktop-app.md) | **下一篇**: [最佳实践](07-best-practices.md)