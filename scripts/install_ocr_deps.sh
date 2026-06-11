#!/bin/bash

################################################################################
# OCR 功能依赖安装脚本（可选）
# 用于安装 OCR 图像识别功能所需的依赖
################################################################################

echo "=== OCR 功能依赖安装脚本 ==="
echo "注意：OCR 功能是可选的，用于扫描版PDF和图片文档识别"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 检查是否在虚拟环境中
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo -e "${GREEN}✓ 虚拟环境已激活: $VIRTUAL_ENV${NC}"
    PYTHON_CMD="python"
    PIP_CMD="pip"
else
    echo -e "${YELLOW}⚠ 未检测到虚拟环境${NC}"
    echo "建议使用虚拟环境来安装OCR依赖"
    read -p "是否继续安装? (y/n): " continue_install
    if [ "$continue_install" != "y" ]; then
        echo "安装已取消"
        exit 0
    fi
    PYTHON_CMD="python3"
    PIP_CMD="pip3"
fi

echo "使用Python: $PYTHON_CMD"
echo "使用pip: $PIP_CMD"
echo ""

# 检查操作系统
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="Linux"
else
    OS="Windows/Other"
fi

echo -e "${BLUE}=== 步骤 1/4: 安装 Python OCR 包 ===${NC}"
echo "安装 OCR Python 依赖..."
$PIP_CMD install paddlepaddle==2.5.2
$PIP_CMD install paddleocr==2.7.0.3
$PIP_CMD install pytesseract==0.3.10
$PIP_CMD install pymupdf==1.23.8
$PIP_CMD install opencv-python==4.8.1.78
$PIP_CMD install pillow==10.1.0

echo ""
echo -e "${BLUE}=== 步骤 2/4: 安装 Tesseract 系统依赖 ===${NC}"

case $OS in
    "macOS")
        echo "检测到 macOS，使用 Homebrew 安装 Tesseract"
        if command -v brew &> /dev/null; then
            brew install tesseract tesseract-lang
        else
            echo -e "${YELLOW}⚠ Homebrew 未安装${NC}"
            echo "请先安装 Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            echo "然后运行此脚本: ./install_ocr_deps.sh"
        fi
        ;;
    "Linux")
        echo "检测到 Linux，使用 apt 安装 Tesseract"
        if command -v apt-get &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra
        elif command -v yum &> /dev/null; then
            sudo yum install -y tesseract
        else
            echo -e "${YELLOW}⚠ 无法检测包管理器${NC}"
            echo "请手动安装 Tesseract"
            echo "Ubuntu/Debian: sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim"
            echo "CentOS/RHEL: sudo yum install tesseract"
        fi
        ;;
    "Windows/Other")
        echo "检测到 Windows 或其他系统"
        echo "请手动安装 Tesseract"
        echo "下载地址: https://github.com/UB-Mannheim/tesseract/wiki"
        ;;
esac

echo ""
echo -e "${BLUE}=== 步骤 3/4: 验证 Python OCR 包安装 ===${NC}"

check_module() {
    local module=$1
    local display_name=$2
    
    output=$($PYTHON_CMD -c "import $module" 2>&1)
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $display_name"
        return 0
    else
        echo -e "${RED}✗${NC} $display_name"
        return 1
    fi
}

check_module "paddleocr" "paddleocr"
check_module "pytesseract" "pytesseract"
check_module "fitz" "pymupdf"
check_module "cv2" "opencv-python"

echo ""
echo -e "${BLUE}=== 步骤 4/4: 验证 Tesseract 安装 ===${NC}"

if command -v tesseract &> /dev/null; then
    tesseract_version=$(tesseract --version 2>&1 | head -n 1)
    echo -e "${GREEN}✓${NC} Tesseract 已安装: $tesseract_version"
    
    # 检查语言包
    echo "已安装的语言包:"
    tesseract --list-langs 2>&1 | head -n 10
else
    echo -e "${RED}✗${NC} Tesseract 未安装"
    echo "请参考上述步骤 2 的安装说明"
fi

echo ""
echo -e "${BLUE}=== OCR 依赖安装完成 ===${NC}"
echo ""
echo "验证安装："
echo "  运行: ./check_prereqs.sh"
echo ""
echo "OCR 功能配置："
echo "  在 config.py 中设置 OCR_ENABLED = True"
echo "  选择 OCR 引擎: OCR_ENGINE = 'paddle' 或 'tesseract'"
echo ""
echo "使用示例："
echo "  python query_interface.py --data ./scanned_docs"
echo ""
echo "注意：OCR 功能是可选的，如果不安装这些依赖，"
echo "      系统会自动禁用 OCR 功能，不影响其他功能的使用。"
