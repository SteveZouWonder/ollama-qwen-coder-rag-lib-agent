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
$PIP_CMD list | grep -E "(llama|chroma|rich|prompt|pypdf|requests|pytest)"
echo ""

# 验证导入
echo "=== 模块导入测试（从 requirements.txt 动态读取）==="
check_module() {
    local module=$1
    local display=$2
    output=$($PYTHON_CMD -c "import $module; print('$module imported successfully')" 2>&1)
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $display${NC}"
    else
        echo -e "${RED}✗ $display${NC}"
    fi
}

# 从 requirements.txt 提取包名并验证
if [ -f "requirements.txt" ]; then
    while IFS= read -r line; do
        # 跳过注释和空行
        if [[ "$line" =~ ^[[:space:]]*# ]] || [[ -z "$line" ]]; then
            continue
        fi
        
        # 提取包名（去除版本要求和注释）
        package_name=$(echo "$line" | sed 's/>=.*//' | sed 's/<.*//' | sed 's/==.*//' | sed 's/~=.*//' | awk '{print $1}')
        
        if [ -n "$package_name" ]; then
            # 转换包名为导入名（例如：python-dotenv -> dotenv）
            import_name=$(echo "$package_name" | sed 's/-/_/g')
            
            # 特殊处理一些包名映射
            case "$package_name" in
                "python-dotenv") import_name="dotenv" ;;
                "prompt-toolkit") import_name="prompt_toolkit" ;;
                "duckduckgo-search") import_name="duckduckgo_search" ;;
                "pytest-cov") import_name="pytest_cov" ;;
                "pytest-xdist") import_name="xdist" ;;
                "beautifulsoup4") import_name="bs4" ;;
                "pillow") import_name="PIL" ;;
                "opencv-python") continue ;; # 跳过opencv-python，导入名复杂
                "gitpython") continue ;; # 跳过gitpython，使用系统git命令
                "llama-index-"*) continue ;; # 跳过llama-index插件包，无法直接导入
                "setuptools"|"wheel") import_name="$package_name" ;; # 保持原名
            esac
            
            # 尝试导入
            check_module "$import_name" "$package_name"
        fi
    done < requirements.txt
else
    echo -e "${YELLOW}⚠ requirements.txt 文件不存在，跳过动态验证${NC}"
    # 回退到硬编码的核心包验证
    echo "使用核心包列表验证..."
    check_module "llama_index" "llama-index"
    check_module "chromadb" "chromadb"
    check_module "rich" "rich"
    check_module "prompt_toolkit" "prompt-toolkit"
    check_module "pypdf" "pypdf"
    check_module "requests" "requests"
fi

# 特别验证网络搜索模块
echo ""
echo "=== 网络搜索功能检查 ==="
if $PYTHON_CMD -c "import sys; sys.path.insert(0, 'src'); from web_search import get_search_engine_manager" 2>/dev/null; then
    echo -e "${GREEN}✓ 网络搜索管理器可用${NC}"
else
    echo -e "${YELLOW}⚠ 网络搜索管理器不可用（可能需要安装 duckduckgo-search）${NC}"
fi

# 测试工具检查
echo ""
echo "=== 测试工具检查 ==="
check_module "pytest" "pytest"
check_module "pytest_cov" "pytest-cov"
check_module "xdist" "pytest-xdist"

echo ""
echo "=== 如果有模块未安装，运行以下命令 ==="
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "  在虚拟环境中运行: ./scripts/install_deps.sh"
else
    echo "  或创建虚拟环境: python3 -m venv venv && source venv/bin/activate && ./scripts/install_deps.sh"
fi