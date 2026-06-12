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
if command -v python3.13 &> /dev/null; then
    PYTHON_CMD="python3.13"
elif command -v python3.14 &> /dev/null; then
    PYTHON_CMD="python3.14"
elif command -v python3.9 &> /dev/null; then
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
            echo -e "${YELLOW}  检测到macOS，推荐使用Homebrew Python以支持最新依赖${NC}"
            echo -e "${YELLOW}  安装命令: brew install python@3.13${NC}"
            echo -e "${YELLOW}  创建虚拟环境: python3.13 -m venv venv${NC}"
        fi
    fi
    
    read -p "是否创建虚拟环境? (y/n): " create_venv
    if [ "$create_venv" = "y" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS 优先使用 python3.13 创建 venv
            if command -v python3.13 &> /dev/null; then
                python3.13 -m venv venv
                source venv/bin/activate
                echo -e "${GREEN}✓ 虚拟环境已创建并激活 (Python 3.13): $VIRTUAL_ENV${NC}"
            elif command -v python3.14 &> /dev/null; then
                python3.14 -m venv venv
                source venv/bin/activate
                echo -e "${GREEN}✓ 虚拟环境已创建并激活 (Python 3.14): $VIRTUAL_ENV${NC}"
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

# 方法1：升级pip和setuptools
echo -e "${BLUE}步骤 1/4: 升级pip、setuptools和wheel${NC}"
$PYTHON_CMD -m $PIP_CMD install --upgrade pip setuptools wheel

# 确保 pkg_resources 可用（修复 setuptools 新版本兼容性问题）
echo -e "${BLUE}步骤 1.5/4: 确保 setuptools 兼容性${NC}"
$PYTHON_CMD -c "from setuptools import setup" 2>/dev/null || {
    echo -e "${YELLOW}⚠ setuptools 版本可能不兼容，尝试重新安装${NC}"
    $PIP_CMD install --force-reinstall setuptools
}

# 方法2：从requirements.txt安装依赖
echo -e "${BLUE}步骤 2/4: 从requirements.txt安装依赖${NC}"
echo "安装依赖（版本号来自requirements.txt）..."

# 先安装数据处理依赖（使用预编译版本，避免构建错误）
echo "步骤 2.1: 安装数据处理依赖..."
if $PIP_CMD install numpy pandas --prefer-binary; then
    echo -e "${GREEN}✓ 数据处理依赖安装成功${NC}"
else
    echo -e "${YELLOW}⚠ 数据处理依赖安装失败，尝试备用方案...${NC}"
    $PIP_CMD install numpy pandas
fi

# 执行安装并捕获错误码
if $PIP_CMD install -r requirements.txt --prefer-binary; then
    echo -e "${GREEN}✓ 核心依赖安装成功${NC}"
    INSTALL_STATUS=0
else
    echo -e "${RED}✗ 核心依赖安装失败${NC}"
    INSTALL_STATUS=1
    echo -e "${YELLOW}尝试使用备用方案...${NC}"
    
    # 备用方案：不使用 --prefer-binary
    echo "尝试不使用 --prefer-binary 选项..."
    if $PIP_CMD install -r requirements.txt; then
        echo -e "${GREEN}✓ 备用方案安装成功${NC}"
        INSTALL_STATUS=0
    else
        echo -e "${RED}✗ 备用方案也失败了${NC}"
        INSTALL_STATUS=1
    fi
fi

# 方法2.5：安装OCR功能依赖（可选）
echo ""
echo -e "${BLUE}是否安装 OCR 功能依赖？${NC}"
echo "OCR 功能用于扫描版 PDF 和图片文档识别"
echo "这会安装额外的依赖：paddlepaddle、paddleocr、pytesseract、pymupdf、opencv-python"
read -p "是否安装 OCR 依赖? (y/n): " install_ocr

if [ "$install_ocr" = "y" ]; then
    echo -e "${BLUE}步骤 2.5/4: 安装 OCR 功能依赖（可选）${NC}"
    echo "安装 OCR 依赖..."
    
    # 注意：paddleocr 在 Python 3.13 上有兼容性问题
    # 我们使用 Tesseract OCR 作为主要 OCR 引擎
    echo "⚠ PaddleOCR 在 Python 3.13 上有兼容性问题"
    echo "安装 Tesseract OCR 相关依赖..."
    
    # 先安装数据处理依赖（如果有）
    if ! $PYTHON_CMD -c "import pandas" 2>/dev/null; then
        echo "安装数据处理依赖..."
        $PIP_CMD install numpy pandas --prefer-binary
    fi
    
    # 安装 OCR 核心依赖（Python 3.13 兼容）
    if $PIP_CMD install pytesseract==0.3.13 pymupdf>=1.25.0 opencv-python==4.9.0.80; then
        echo -e "${GREEN}✓ OCR 依赖安装完成（Tesseract OCR）${NC}"
    else
        echo -e "${RED}✗ OCR 依赖安装失败${NC}"
        echo -e "${YELLOW}跳过 OCR 依赖安装，可以稍后手动安装${NC}"
        echo "手动安装命令: pip install pytesseract==0.3.13 pymupdf>=1.25.0 opencv-python==4.9.0.80"
    fi
else
    echo -e "${YELLOW}⚠ 跳过 OCR 依赖安装${NC}"
    echo "  提示: 如需使用 OCR 功能，可以运行: pip install pytesseract==0.3.13 pymupdf>=1.25.0 opencv-python==4.9.0.80"
    echo "  注意: 当前使用 Python 3.13，PaddleOCR 有兼容性问题，建议使用 Tesseract OCR"
fi

# 方法3：验证安装
echo -e "${BLUE}步骤 3/4: 检查安装状态${NC}"

# 检查核心安装状态
if [ "$INSTALL_STATUS" -ne 0 ]; then
    echo -e "${RED}✗ 核心依赖安装失败，跳过验证步骤${NC}"
    echo -e "${YELLOW}请查看上述错误信息，并尝试以下解决方案：${NC}"
    echo "1. 清理 pip 缓存: pip cache purge"
    echo "2. 重新安装: pip install -r requirements.txt --no-cache-dir"
    echo "3. 手动安装失败的包"
    echo "4. 使用预编译包: pip install -r requirements.txt --prefer-binary"
    echo ""
    echo -e "${RED}安装未完成，请解决上述问题后重新运行安装脚本${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 依赖安装成功，开始验证...${NC}"
echo ""
echo -e "${BLUE}步骤 4/4: 验证安装${NC}"

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
echo -e "${BLUE}=== 安装完成 ===${NC}"
echo ""
echo "验证安装："
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "  在虚拟环境中运行: ./scripts/check_prereqs.sh"
    echo "  或者: source venv/bin/activate && ./scripts/check_prereqs.sh"
else
    echo "  运行: ./scripts/check_prereqs.sh"
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
echo "   brew install python@3.13"
echo "   python3.13 -m venv venv"
echo "   source venv/bin/activate"
echo "   pip install -r requirements.txt"
echo ""
echo "注意: 版本号在 requirements.txt 中统一管理，如需升级请修改该文件"
