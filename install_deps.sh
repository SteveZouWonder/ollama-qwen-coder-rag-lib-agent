#!/bin/bash

################################################################################
# 依赖安装脚本 - 解决依赖冲突问题
################################################################################

echo "=== 依赖安装脚本 ==="

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 检查虚拟环境
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${YELLOW}⚠ 未检测到虚拟环境，建议使用虚拟环境${NC}"
    echo -e "${YELLOW}  使用虚拟环境可以避免依赖冲突和环境问题${NC}"
    read -p "是否创建虚拟环境? (y/n): " create_venv
    if [ "$create_venv" = "y" ]; then
        $PYTHON_CMD -m venv venv
        source venv/bin/activate
        echo -e "${GREEN}✓ 虚拟环境已创建并激活: $VIRTUAL_ENV${NC}"
    else
        echo -e "${YELLOW}⚠ 将使用系统Python环境安装依赖${NC}"
        echo -e "${YELLOW}  这可能导致依赖冲突，建议使用虚拟环境${NC}"
    fi
else
    echo -e "${GREEN}✓ 虚拟环境已激活: $VIRTUAL_ENV${NC}"
fi

# 确定使用的Python命令
if [[ "$VIRTUAL_ENV" != "" ]]; then
    PYTHON_CMD="python"
    PIP_CMD="pip"
else
    PYTHON_CMD="$PYTHON_CMD"
    PIP_CMD="pip3"
fi

echo "使用Python: $PYTHON_CMD"
echo "使用pip: $PIP_CMD"

# 方法1：升级pip
echo -e "${BLUE}步骤 1/4: 升级pip和setuptools${NC}"
$PYTHON_CMD -m $PIP_CMD install --upgrade pip setuptools wheel

# 方法2：分步安装核心依赖
echo -e "${BLUE}步骤 2/4: 分步安装核心依赖${NC}"

# 先安装banks（导致问题的包）
echo "安装banks..."
$PIP_CMD install "banks==2.4.0"

# 然后安装其他核心依赖
echo "安装chromadb..."
$PIP_CMD install "chromadb==0.4.22"

echo "安装pypdf..."
$PIP_CMD install "pypdf==4.3.1"

echo "安装requests..."
$PIP_CMD install "requests==2.32.3"

echo "安装urllib3..."
$PIP_CMD install "urllib3<2.0.0"  # 使用v1.x版本避免LibreSSL兼容性警告

echo "安装python-dotenv..."
$PIP_CMD install "python-dotenv==1.0.1"

echo "安装rich..."
$PIP_CMD install "rich==13.9.4"

echo "安装prompt-toolkit..."
$PIP_CMD install "prompt-toolkit==3.0.48"

# 方法3：安装llama-index相关依赖
echo -e "${BLUE}步骤 3/4: 安装llama-index相关依赖${NC}"

# 先安装llama-index核心
echo "安装llama-index核心..."
$PIP_CMD install "llama-index==0.10.46"

# 然后安装各个扩展包
echo "安装llama-index扩展包..."
$PIP_CMD install "llama-index-embeddings-ollama==0.1.3"
$PIP_CMD install "llama-index-llms-ollama==0.2.0"
$PIP_CMD install "llama-index-readers-file==0.1.4"
$PIP_CMD install "llama-index-vector-stores-chroma==0.1.8"

# 方法4：验证安装
echo -e "${BLUE}步骤 4/4: 验证安装${NC}"

echo "验证关键依赖..."
$PYTHON_CMD -c "import llama_index" 2>/dev/null && echo -e "${GREEN}✓ llama-index${NC}" || echo -e "${RED}✗ llama-index${NC}"
$PYTHON_CMD -c "import chromadb" 2>/dev/null && echo -e "${GREEN}✓ chromadb${NC}" || echo -e "${RED}✗ chromadb${NC}"
$PYTHON_CMD -c "import pypdf" 2>/dev/null && echo -e "${GREEN}✓ pypdf${NC}" || echo -e "${RED}✗ pypdf${NC}"
$PYTHON_CMD -c "import rich" 2>/dev/null && echo -e "${GREEN}✓ rich${NC}" || echo -e "${RED}✗ rich${NC}"
$PYTHON_CMD -c "import prompt_toolkit" 2>/dev/null && echo -e "${GREEN}✓ prompt-toolkit${NC}" || echo -e "${RED}✗ prompt-toolkit${NC}"

echo ""
echo -e "${BLUE}=== 安装完成 ===${NC}"
echo ""
echo "验证安装："
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "  请在虚拟环境中运行: ./check_prereqs.sh"
    echo "  或者直接运行: source venv/bin/activate && ./check_prereqs.sh"
else
    echo "  运行: ./check_prereqs.sh"
    echo "  注意: 如果没有使用虚拟环境，可能需要使用 sudo"
fi
echo ""
echo "如果验证失败，请尝试以下替代方案："
echo "1. 使用 --no-cache-dir: pip install -r requirements.txt --no-cache-dir"
echo "2. 使用 --prefer-binary: pip install -r requirements.txt --prefer-binary"
echo "3. 使用备用配置: pip install -r requirements_alternative.txt"
echo "4. 创建新的虚拟环境重新开始"
