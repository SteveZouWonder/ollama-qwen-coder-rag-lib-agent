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

# 确定默认Python命令
PYTHON_CMD="python3"
if command -v python3.9 &> /dev/null; then
    PYTHON_CMD="python3.9"
fi

# 检查虚拟环境
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${YELLOW}⚠ 未检测到虚拟环境，建议使用虚拟环境${NC}"
    echo -e "${YELLOW}  使用虚拟环境可以避免依赖冲突和环境问题${NC}"
    
    # 检测macOS并推荐Homebrew Python
    if [[ "$OSTYPE" == "darwin"* ]]; then
        python_path=$(which python3 2>/dev/null)
        if [[ "$python_path" != *"homebrew"* ]]; then
            echo -e "${YELLOW}  检测到macOS，推荐使用Homebrew Python以支持urllib3 2.6.3${NC}"
            echo -e "${YELLOW}  安装命令: brew install python@3.9${NC}"
            echo -e "${YELLOW}  创建虚拟环境: python3.9 -m venv venv_homebrew${NC}"
        fi
    fi
    
    read -p "是否创建虚拟环境? (y/n): " create_venv
    if [ "$create_venv" = "y" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS 推荐使用 python3.9 创建 venv_homebrew
            if command -v python3.9 &> /dev/null; then
                python3.9 -m venv venv_homebrew
                source venv_homebrew/bin/activate
                echo -e "${GREEN}✓ 虚拟环境已创建并激活 (Homebrew Python): $VIRTUAL_ENV${NC}"
            else
                python3 -m venv venv
                source venv/bin/activate
                echo -e "${GREEN}✓ 虚拟环境已创建并激活: $VIRTUAL_ENV${NC}"
                echo -e "${YELLOW}  提示: 考虑使用Homebrew Python以获得更好的兼容性${NC}"
            fi
        else
            python3 -m venv venv
            source venv/bin/activate
            echo -e "${GREEN}✓ 虚拟环境已创建并激活: $VIRTUAL_ENV${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ 将使用系统Python环境安装依赖${NC}"
        echo -e "${YELLOW}  这可能导致依赖冲突，建议使用虚拟环境${NC}"
    fi
else
    echo -e "${GREEN}✓ 虚拟环境已激活: $VIRTUAL_ENV${NC}"
    # 检查是否为Homebrew Python
    if [[ "$OSTYPE" == "darwin"* ]]; then
        python_path=$(which python 2>/dev/null)
        if [[ "$python_path" == *"homebrew"* ]]; then
            echo -e "${GREEN}✓ 使用 Homebrew Python (推荐用于 urllib3 2.x 支持)${NC}"
        fi
    fi
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

# 检查requirements.txt文件
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}✗ requirements.txt 文件不存在${NC}"
    exit 1
fi

# 方法1：升级pip
echo -e "${BLUE}步骤 1/3: 升级pip和setuptools${NC}"
$PYTHON_CMD -m $PIP_CMD install --upgrade pip setuptools wheel

# 方法2：从requirements.txt安装依赖
echo -e "${BLUE}步骤 2/3: 从requirements.txt安装依赖${NC}"
echo "安装依赖（版本号来自requirements.txt）..."
$PIP_CMD install -r requirements.txt

# 方法3：验证安装
echo -e "${BLUE}步骤 3/3: 验证安装${NC}"

echo "验证核心依赖..."
$PYTHON_CMD -c "import llama_index" 2>/dev/null && echo -e "${GREEN}✓ llama-index${NC}" || echo -e "${RED}✗ llama-index${NC}"
$PYTHON_CMD -c "import chromadb" 2>/dev/null && echo -e "${GREEN}✓ chromadb${NC}" || echo -e "${RED}✗ chromadb${NC}"
$PYTHON_CMD -c "import pypdf" 2>/dev/null && echo -e "${GREEN}✓ pypdf${NC}" || echo -e "${RED}✗ pypdf${NC}"
$PYTHON_CMD -c "import rich" 2>/dev/null && echo -e "${GREEN}✓ rich${NC}" || echo -e "${RED}✗ rich${NC}"
$PYTHON_CMD -c "import prompt_toolkit" 2>/dev/null && echo -e "${GREEN}✓ prompt-toolkit${NC}" || echo -e "${RED}✗ prompt-toolkit${NC}"
$PYTHON_CMD -c "import requests" 2>/dev/null && echo -e "${GREEN}✓ requests${NC}" || echo -e "${RED}✗ requests${NC}"
$PYTHON_CMD -c "import dotenv" 2>/dev/null && echo -e "${GREEN}✓ python-dotenv${NC}" || echo -e "${RED}✗ python-dotenv${NC}"
$PYTHON_CMD -c "import urllib3" 2>/dev/null && echo -e "${GREEN}✓ urllib3${NC}" || echo -e "${RED}✗ urllib3${NC}"

# 检查urllib3 SSL兼容性
echo "检查urllib3 SSL兼容性..."
if $PYTHON_CMD -c "import ssl; print(ssl.OPENSSL_VERSION)" 2>/dev/null | grep -q "LibreSSL"; then
    urllib3_version=$($PYTHON_CMD -c "import urllib3; print(urllib3.__version__)" 2>/dev/null)
    if [[ "$urllib3_version" == "2."* ]]; then
        echo -e "${YELLOW}⚠ urllib3 2.x 与 LibreSSL 不兼容，可能需要降级或使用Homebrew Python${NC}"
    fi
fi

echo ""
echo "验证测试工具（可选）..."
$PYTHON_CMD -c "import pytest" 2>/dev/null && echo -e "${GREEN}✓ pytest${NC}" || echo -e "${YELLOW}⚠ pytest未安装（测试工具可选）${NC}"
$PYTHON_CMD -c "import pytest_cov" 2>/dev/null && echo -e "${GREEN}✓ pytest-cov${NC}" || echo -e "${YELLOW}⚠ pytest-cov未安装（测试工具可选）${NC}"

echo ""
echo "验证OCR功能（可选）..."
$PYTHON_CMD -c "import paddleocr" 2>/dev/null && echo -e "${GREEN}✓ paddleocr${NC}" || echo -e "${YELLOW}⚠ paddleocr未安装（OCR功能可选）${NC}"
$PYTHON_CMD -c "import pytesseract" 2>/dev/null && echo -e "${GREEN}✓ pytesseract${NC}" || echo -e "${YELLOW}⚠ pytesseract未安装（OCR功能可选）${NC}"
$PYTHON_CMD -c "import fitz" 2>/dev/null && echo -e "${GREEN}✓ pymupdf${NC}" || echo -e "${YELLOW}⚠ pymupdf未安装（OCR功能可选）${NC}"
$PYTHON_CMD -c "import cv2" 2>/dev/null && echo -e "${GREEN}✓ opencv-python${NC}" || echo -e "${YELLOW}⚠ opencv-python未安装（OCR功能可选）${NC}"

# 检查Tesseract系统级依赖
if command -v tesseract &> /dev/null; then
    tesseract_version=$(tesseract --version 2>&1 | head -n 1)
    echo -e "${GREEN}✓ tesseract${NC} ($tesseract_version)"
else
    echo -e "${YELLOW}⚠ tesseract未安装（OCR功能可选）${NC}"
fi

echo ""
echo -e "${BLUE}=== 安装完成 ===${NC}"
echo ""
echo "验证安装："
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "  在虚拟环境中运行: ./check_prereqs.sh"
    if [[ "$VIRTUAL_ENV" == *"venv_homebrew"* ]]; then
        echo "  或者: source venv_homebrew/bin/activate && ./check_prereqs.sh"
    else
        echo "  或者: source venv/bin/activate && ./check_prereqs.sh"
    fi
else
    echo "  运行: ./check_prereqs.sh"
    echo "  注意: 如果没有使用虚拟环境，可能需要使用 sudo"
fi
echo ""
echo "快速开始命令："
echo "  python query_interface.py --data ./data"
echo "  python desktop_app.py --status"
echo "  python desktop_app.py --warm-up"
echo ""
echo "如果验证失败，请尝试以下替代方案："
echo "1. 使用 --no-cache-dir: pip install -r requirements.txt --no-cache-dir"
echo "2. 使用 --prefer-binary: pip install -r requirements.txt --prefer-binary"
echo "3. macOS用户: 使用Homebrew Python创建新虚拟环境"
echo "   brew install python@3.9"
echo "   python3.9 -m venv venv_homebrew"
echo "   source venv_homebrew/bin/activate"
echo "   pip install -r requirements.txt"
echo ""
echo "注意: 版本号在 requirements.txt 中统一管理，如需升级请修改该文件"
