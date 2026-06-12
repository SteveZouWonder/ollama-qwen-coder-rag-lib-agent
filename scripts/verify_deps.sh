#!/bin/bash

################################################################################
# 快速依赖验证脚本
# 用于验证依赖是否正确安装
################################################################################

echo "=== 依赖验证脚本 ==="

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查虚拟环境
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo -e "${GREEN}✓ 虚拟环境已激活: $VIRTUAL_ENV${NC}"
    PYTHON_CMD="python"
else
    echo -e "${YELLOW}⚠ 使用系统Python环境${NC}"
    PYTHON_CMD="python3"
fi

echo "Python命令: $PYTHON_CMD"
echo "Python路径: $(which $PYTHON_CMD)"
echo ""

# 检查pip
if command -v pip &> /dev/null; then
    PIP_CMD="pip"
    echo "pip命令: $PIP_CMD"
    echo "pip路径: $(which $PIP_CMD)"
elif command -v pip3 &> /dev/null; then
    PIP_CMD="pip3"
    echo "pip3命令: $PIP_CMD"
    echo "pip3路径: $(which $PIP_CMD)"
fi
echo ""

# 检查已安装的包
echo "=== 已安装的Python包 ==="
$PIP_CMD list | grep -E "(llama|chroma|rich|prompt|pypdf|requests)"
echo ""

# 验证导入
echo "=== 模块导入测试 ==="
check_module() {
    local module=$1
    local display=$2
    output=$($PYTHON_CMD -c "import $module; print('$module imported successfully')" 2>&1)
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $display${NC}: $output"
    else
        echo -e "${RED}✗ $display${NC}: $output"
    fi
}

check_module "llama_index" "llama-index"
check_module "chromadb" "chromadb"
check_module "rich" "rich"
check_module "prompt_toolkit" "prompt-toolkit"
check_module "pypdf" "pypdf"
check_module "requests" "requests"

echo ""
echo "=== 如果有模块未安装，运行以下命令 ==="
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "  在虚拟环境中运行: ./scripts/install_deps.sh"
else
    echo "  或创建虚拟环境: python3 -m venv venv && source venv/bin/activate && ./scripts/install_deps.sh"
fi