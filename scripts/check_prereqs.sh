#!/bin/bash

################################################################################
# 前置条件检查脚本
# 用于验证智能文档+代码助手项目所需的所有前置条件
################################################################################

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 统计变量
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# 问题分类统计
PYTHON_ISSUES=0
OLLAMA_ISSUES=0
DEPENDENCY_ISSUES=0
NETWORK_ISSUES=0

# 打印标题
print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# 打印检查结果
print_result() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $2"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    elif [ $1 -eq 1 ]; then
        echo -e "${RED}✗${NC} $2"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    else
        echo -e "${YELLOW}⚠${NC} $2"
        WARNING_CHECKS=$((WARNING_CHECKS + 1))
    fi
}

# 检查命令是否存在
check_command() {
    if command -v $1 &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# 检查Python版本
check_python() {
    if check_command python3.13; then
        python3.13 --version &> /dev/null
        if [ $? -eq 0 ]; then
            version=$(python3.13 --version 2>&1 | awk '{print $2}')
            print_result 0 "Python 版本: $version (推荐 3.13.13)"
            return 0
        else
            print_result 1 "Python3.13 不可用"
            PYTHON_ISSUES=$((PYTHON_ISSUES + 1))
            return 1
        fi
    fi
    
    # 检查其他 Python 版本作为备选
    if check_command python3; then
        python3 --version &> /dev/null
        if [ $? -eq 0 ]; then
            version=$(python3 --version 2>&1 | awk '{print $2}')
            major=$(echo $version | cut -d. -f1)
            minor=$(echo $version | cut -d. -f2)
            
            if [ $major -gt 3 ] || ([ $major -eq 3 ] && [ $minor -ge 13 ]); then
                print_result 0 "Python 版本: $version (推荐 3.13+)"
                
                # 检查是否为 Homebrew Python (macOS 用户推荐)
                if [[ "$OSTYPE" == "darwin"* ]]; then
                    python_path=$(which python3 2>/dev/null)
                    if [[ "$python_path" == *"homebrew"* ]]; then
                        print_result 0 "使用 Homebrew Python (推荐)"
                    else
                        print_result 2 "未使用 Homebrew Python (macOS 用户推荐)"
                        echo "  建议: brew install python@3.13 以获得最佳兼容性"
                        echo "  当前路径: $python_path"
                    fi
                fi
                return 0
            else
                print_result 1 "Python 版本过低: $version (需要 3.13+)"
                PYTHON_ISSUES=$((PYTHON_ISSUES + 1))
                echo "  建议: brew install python@3.13 或使用 pyenv 安装 Python 3.13.13"
                return 1
            fi
        else
            print_result 1 "Python3 不可用"
            PYTHON_ISSUES=$((PYTHON_ISSUES + 1))
            return 1
        fi
    else
        print_result 1 "Python3 未安装"
        PYTHON_ISSUES=$((PYTHON_ISSUES + 1))
        return 1
    fi
}

# 检查pip
check_pip() {
    if check_command pip3; then
        pip3 --version &> /dev/null
        if [ $? -eq 0 ]; then
            version=$(pip3 --version 2>&1 | awk '{print $2}')
            print_result 0 "pip3 版本: $version"
            return 0
        else
            print_result 1 "pip3 不可用"
            return 1
        fi
    else
        print_result 1 "pip3 未安装"
        return 1
    fi
}

# 检查Ollama
check_ollama() {
    if check_command ollama; then
        print_result 0 "Ollama 已安装"
        
        # 检查版本
        version=$(ollama --version 2>&1)
        echo "  版本: $version"
        
        # 检查服务状态
        if curl -s http://localhost:11434/api/tags &> /dev/null; then
            print_result 0 "Ollama 服务运行中 (端口 11434)"
        else
            print_result 1 "Ollama 服务未运行"
            echo "  请运行: ollama serve"
            OLLAMA_ISSUES=$((OLLAMA_ISSUES + 1))
        fi
        
        # 检查模型
        echo "  已安装的模型:"
        models=$(ollama list 2>&1)
        if echo "$models" | grep -q "qwen2.5-coder"; then
            print_result 0 "qwen2.5-coder 模型已安装"
        else
            print_result 1 "qwen2.5-coder 模型未安装"
            echo "  请运行: ollama pull qwen2.5-coder:7b"
            OLLAMA_ISSUES=$((OLLAMA_ISSUES + 1))
        fi
        
        if echo "$models" | grep -q "nomic-embed-text"; then
            print_result 0 "nomic-embed-text 模型已安装"
        else
            print_result 1 "nomic-embed-text 模型未安装"
            echo "  请运行: ollama pull nomic-embed-text:latest"
            OLLAMA_ISSUES=$((OLLAMA_ISSUES + 1))
        fi
        
        return 0
    else
        print_result 1 "Ollama 未安装"
        echo "  请访问: https://ollama.com/download"
        OLLAMA_ISSUES=$((OLLAMA_ISSUES + 1))
        return 1
    fi
}

# 检查Git
check_git() {
    if check_command git; then
        version=$(git --version 2>&1)
        print_result 0 "Git 版本: $version"
        return 0
    else
        print_result 2 "Git 未安装 (可选)"
        return 2
    fi
}

# 检查curl
check_curl() {
    if check_command curl; then
        version=$(curl --version 2>&1 | head -n 1)
        print_result 0 "curl 已安装: $version"
        return 0
    else
        print_result 1 "curl 未安装"
        return 1
    fi
}

# 检查系统内存
check_memory() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        mem_total=$(free -m | awk 'NR==2{print $2}')
        mem_free=$(free -m | awk 'NR==2{print $7}')
        
        if [ $mem_total -gt 8192 ]; then
            print_result 0 "系统内存: ${mem_total}MB (可用: ${mem_free}MB)"
        else
            print_result 1 "系统内存不足: ${mem_total}MB (建议 > 8GB)"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        mem_total=$(( $(sysctl -n hw.memsize) / 1024 / 1024 ))
        # 简化macOS的内存检查，使用系统命令获取可用内存
        mem_free=$(vm_stat | grep "Pages free" | awk '{print $3}' | sed 's/\.//')
        
        if [ $mem_total -gt 8192 ]; then
            print_result 0 "系统内存: ${mem_total}MB"
        else
            print_result 1 "系统内存不足: ${mem_total}MB (建议 > 8GB)"
        fi
    else
        print_result 2 "无法检测系统内存 (Windows)"
    fi
}

# 检查磁盘空间
check_disk() {
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        print_result 2 "无法检测磁盘空间 (Windows)"
    else
        # 简化的磁盘检查，只验证目录可写
        if [ -w . ]; then
            print_result 0 "当前目录可写"
        else
            print_result 1 "当前目录不可写"
        fi
    fi
}

# 检查Python依赖
check_dependencies() {
    if [ ! -f "requirements.txt" ]; then
        print_result 1 "requirements.txt 文件不存在"
        return 1
    fi
    
    # 检查虚拟环境
    if [[ "$VIRTUAL_ENV" != "" ]]; then
        print_result 0 "虚拟环境已激活: $VIRTUAL_ENV"
        PYTHON_CMD="python"
    else
        print_result 2 "未检测到虚拟环境 (推荐使用)"
        PYTHON_CMD="python3"
        echo "  提示: 使用虚拟环境可以避免依赖冲突"
        echo "  创建方法: python3.13 -m venv venv && source venv/bin/activate"
        echo "  macOS 用户推荐: brew install python@3.13 && python3.13 -m venv venv && source venv/bin/activate"
    fi
    
    # 检查pip命令
    if command -v pip &> /dev/null; then
        PIP_CMD="pip"
    elif command -v pip3 &> /dev/null; then
        PIP_CMD="pip3"
    else
        print_result 1 "pip未安装"
        echo "  请运行: $PYTHON_CMD -m ensurepip --upgrade"
        return 1
    fi
    
    # 尝试导入关键模块并获取详细错误信息
    check_module() {
        local module=$1
        local display_name=$2
        
        output=$($PYTHON_CMD -c "import $module" 2>&1)
        exit_code=$?
        
        if [ $exit_code -eq 0 ]; then
            print_result 0 "$display_name 已安装"
            return 0
        else
            print_result 1 "$display_name 未安装"
            
            # 根据错误信息提供针对性建议
            if echo "$output" | grep -q "ModuleNotFoundError"; then
                echo "  错误: 模块未找到"
                echo "  解决方案: $PIP_CMD install $module"
            elif echo "$output" | grep -q "ImportError"; then
                echo "  错误: 依赖导入失败"
                echo "  解决方案: $PIP_CMD install --upgrade $module"
            elif echo "$output" | grep -q "Permission denied"; then
                echo "  错误: 权限不足"
                echo "  解决方案: 使用虚拟环境或 sudo $PIP_CMD install"
            else
                echo "  错误: $output"
                echo "  解决方案: $PIP_CMD install -r requirements.txt"
            fi
            return 1
        fi
    }
    
    # 检查关键依赖
    local dep_failures=0
    check_module "llama_index" "llama-index" || dep_failures=$((dep_failures + 1))
    check_module "chromadb" "chromadb" || dep_failures=$((dep_failures + 1))
    check_module "rich" "rich" || dep_failures=$((dep_failures + 1))
    check_module "prompt_toolkit" "prompt-toolkit" || dep_failures=$((dep_failures + 1))
    check_module "pypdf" "pypdf" || dep_failures=$((dep_failures + 1))
    check_module "requests" "requests" || dep_failures=$((dep_failures + 1))
    check_module "dotenv" "python-dotenv" || dep_failures=$((dep_failures + 1))
    
    # 检查测试工具
    check_module "pytest" "pytest" || dep_failures=$((dep_failures + 1))
    check_module "pytest_cov" "pytest-cov" || dep_failures=$((dep_failures + 1))
    check_module "xdist" "pytest-xdist" || dep_failures=$((dep_failures + 1))
    
    # 检查新功能依赖
    check_module "urllib3" "urllib3" || dep_failures=$((dep_failures + 1))
    if [ $dep_failures -eq 0 ]; then
        # 检查 urllib3 版本兼容性
        urllib3_version=$($PYTHON_CMD -c "import urllib3; print(urllib3.__version__)" 2>&1)
        echo "  urllib3 版本: $urllib3_version"
        
        # 检查 SSL 兼容性
        ssl_check=$($PYTHON_CMD -c "import ssl; print(ssl.OPENSSL_VERSION)" 2>&1)
        if [[ "$ssl_check" == *"LibreSSL"* ]] && [[ "$urllib3_version" == "2."* ]]; then
            print_result 1 "urllib3 2.x 与 LibreSSL 不兼容"
            echo "  建议: 使用 Homebrew Python 或降级 urllib3 到 1.26.20"
            dep_failures=$((dep_failures + 1))
        else
            print_result 0 "urllib3 SSL 兼容性正常"
        fi
    fi
    
    # 检查桌面应用依赖（必需）
    output=$($PYTHON_CMD -c "import pystray" 2>&1)
    if [ $? -ne 0 ]; then
        print_result 1 "pystray 未安装 (桌面应用必需)"
        echo "  解决方案: pip install pystray"
        dep_failures=$((dep_failures + 1))
    else
        print_result 0 "pystray 已安装"
    fi
    
    output=$($PYTHON_CMD -c "import PIL" 2>&1)
    if [ $? -ne 0 ]; then
        print_result 1 "PIL/pillow 未安装 (桌面应用必需)"
        echo "  解决方案: pip install pillow"
        dep_failures=$((dep_failures + 1))
    else
        print_result 0 "PIL/pillow 已安装"
    fi
    
    # 检查测试工具（可选）
    output=$($PYTHON_CMD -c "import pytest" 2>&1)
    if [ $? -ne 0 ]; then
        print_result 2 "pytest 未安装 (测试工具可选)"
        echo "  提示: pip install pytest 用于运行测试"
    else
        print_result 0 "pytest 已安装 (测试工具)"
    fi
    
    output=$($PYTHON_CMD -c "import pytest_cov" 2>&1)
    if [ $? -ne 0 ]; then
        print_result 2 "pytest-cov 未安装 (测试工具可选)"
        echo "  提示: pip install pytest-cov 用于测试覆盖率"
    else
        print_result 0 "pytest-cov 已安装 (测试工具)"
    fi
    
    if [ $dep_failures -gt 0 ]; then
        DEPENDENCY_ISSUES=$((DEPENDENCY_ISSUES + dep_failures))
        echo ""
        echo "  提示: 运行 ./scripts/install_deps.sh 自动解决依赖问题"
    fi
}

# 检查OCR功能依赖（可选）
check_ocr_dependencies() {
    if [ ! -f "requirements.txt" ]; then
        print_result 1 "requirements.txt 文件不存在"
        return 1
    fi
    
    # 检查虚拟环境
    if [[ "$VIRTUAL_ENV" != "" ]]; then
        PYTHON_CMD="python"
    else
        PYTHON_CMD="python3"
    fi
    
    # 检查pip命令
    if command -v pip &> /dev/null; then
        PIP_CMD="pip"
    elif command -v pip3 &> /dev/null; then
        PIP_CMD="pip3"
    else
        print_result 1 "pip未安装"
        return 1
    fi
    
    echo "  OCR 功能是可选的，用于扫描版PDF和图片文档识别"
    echo "  当前使用 Python 3.13，推荐使用 Tesseract OCR（兼容性更好）"
    echo "  如需启用OCR功能，请安装以下依赖："
    
    # 检查OCR Python包
    ocr_module_failures=0
    
    # 检查 Tesseract OCR 相关包（Python 3.13 兼容）
    check_module "pytesseract" "pytesseract" || ocr_module_failures=$((ocr_module_failures + 1))
    check_module "fitz" "pymupdf" || ocr_module_failures=$((ocr_module_failures + 1))
    check_module "cv2" "opencv-python" || ocr_module_failures=$((ocr_module_failures + 1))
    
    # 检查数据处理依赖（现在在 requirements.txt 中）
    check_module "numpy" "numpy" || ocr_module_failures=$((ocr_module_failures + 1))
    check_module "pandas" "pandas" || ocr_module_failures=$((ocr_module_failures + 1))
    
    # 检查 opencv-python 兼容性
    opencv_check_result=$($PYTHON_CMD -c "import cv2; print(cv2.__version__)" 2>&1)
    if [ $? -eq 0 ]; then
        print_result 0 "opencv-python 已安装 (版本: $opencv_check_result)"
        
        # 检查 opencv-python 与 NumPy 的兼容性
        numpy_version=$($PYTHON_CMD -c "import numpy; print(numpy.__version__)" 2>&1)
        # 检查 numpy 版本是否 >= 2.0
        if [[ "$numpy_version" == 2.* ]]; then
            print_result 0 "opencv-python 与 NumPy 2.x 兼容"
        else
            print_result 2 "opencv-python 可能与 NumPy $numpy_version 不兼容"
            echo "  建议: pip install --upgrade opencv-python>=4.13.0"
        fi
    else
        print_result 1 "opencv-python 未安装或与 NumPy 2.x 不兼容"
        echo "  解决方案: pip install --upgrade opencv-python>=4.13.0"
        echo "  或者: pip install opencv-python-headless (无GUI版本)"
        ocr_module_failures=$((ocr_module_failures + 1))
    fi
    
    # 检查Tesseract系统级依赖
    if command -v tesseract &> /dev/null; then
        tesseract_version=$(tesseract --version 2>&1 | head -n 1)
        print_result 0 "tesseract 已安装: $tesseract_version"
    else
        print_result 2 "tesseract 未安装 (OCR功能可选)"
        echo "  macOS 安装: brew install tesseract tesseract-lang"
        echo "  Linux 安装: sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim"
        echo "  Windows 安装: https://github.com/UB-Mannheim/tesseract/wiki"
        ocr_module_failures=$((ocr_module_failures + 1))
    fi
    
    # 总结OCR依赖状态
    if [ $ocr_module_failures -eq 0 ]; then
        print_result 0 "OCR Python依赖完整 (Tesseract OCR + NumPy 2.x 兼容)"
        echo "  OCR 功能已可用：扫描版PDF和图片识别"
    else
        print_result 2 "OCR Python依赖不完整 (功能可选)"
        echo "  安装OCR依赖: pip install pytesseract pymupdf opencv-python>=4.13.0"
        echo "  或运行主安装脚本: ./scripts/install_deps.sh (会提示是否安装OCR依赖)"
        echo "  不影响核心功能使用，只在需要OCR时安装"
        echo "  注意: opencv-python 需要 >=4.13.0 版本以兼容 NumPy 2.x"
        echo "  注意: 当前使用 Python 3.13，PaddleOCR 有兼容性问题，建议使用 Tesseract OCR"
    fi
}

# 检查项目文件
check_project_files() {
    required_files=(
        "config.py"
        "query_interface.py"
        "rag_engine.py"
        "react_engine.py"
        "agent_tools.py"
        "document_loader.py"
        "desktop_app.py"
        "knowledge_snapshot.py"
        "knowledge_to_skills.py"
        "content_security.py"
        "chat_history.py"
    )
    
    missing_files=0
    for file in "${required_files[@]}"; do
        if [ -f "$file" ]; then
            : # 文件存在
        else
            echo -e "${RED}✗${NC} 缺少文件: $file"
            missing_files=$((missing_files + 1))
        fi
    done
    
    if [ $missing_files -eq 0 ]; then
        print_result 0 "所有项目文件完整"
    else
        print_result 1 "缺少 $missing_files 个项目文件"
    fi
}

# 检查网络连接
check_network() {
    local network_issues=0
    if curl -s --connect-timeout 5 https://www.google.com &> /dev/null; then
        print_result 0 "网络连接正常"
    else
        print_result 1 "网络连接异常"
        echo "  请检查网络设置或代理配置"
        network_issues=$((network_issues + 1))
    fi
    
    # 检查Ollama API
    if curl -s --connect-timeout 5 http://localhost:11434/api/tags &> /dev/null; then
        print_result 0 "Ollama API 可访问"
    else
        print_result 1 "Ollama API 不可访问"
        echo "  请确保 Ollama 服务正在运行"
        network_issues=$((network_issues + 1))
    fi
    
    if [ $network_issues -gt 0 ]; then
        NETWORK_ISSUES=$((NETWORK_ISSUES + network_issues))
    fi
}

# 主函数
main() {
    print_header "前置条件检查开始"
    
    # 基础命令检查
    print_header "基础命令检查"
    check_python
    check_pip
    check_git
    check_curl
    
    # 系统资源检查
    print_header "系统资源检查"
    check_memory
    check_disk
    
    # Ollama检查
    print_header "Ollama 检查"
    check_ollama
    
    # Python依赖检查
    print_header "Python 依赖检查"
    check_dependencies
    
    # OCR功能检查（可选）
    print_header "OCR 功能检查（可选）"
    check_ocr_dependencies
    
    # 项目文件检查
    print_header "项目文件检查"
    check_project_files
    
    # 网络检查
    print_header "网络检查"
    check_network
    
    # 总结
    print_header "检查总结"
    echo -e "总检查项: $TOTAL_CHECKS"
    echo -e "${GREEN}通过: $PASSED_CHECKS${NC}"
    echo -e "${RED}失败: $FAILED_CHECKS${NC}"
    echo -e "${YELLOW}警告: $WARNING_CHECKS${NC}"
    
    if [ $FAILED_CHECKS -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✓ 所有必要条件已满足，可以开始使用！${NC}"
        echo ""
        echo "快速开始命令："
        echo "  python desktop_app.py              # 启动桌面应用（推荐）"
        echo "  python desktop_app.py --status     # 检查服务状态"
        echo "  python desktop_app.py --warm-up    # 预热模型"
        echo "  python query_interface.py --data ./data  # 命令行模式"
        return 0
    else
        echo ""
        echo -e "${RED}✗ 发现 $FAILED_CHECKS 个问题，请按以下顺序解决：${NC}"
        echo ""
        
        # 根据问题类型提供针对性建议
        if [ $PYTHON_ISSUES -gt 0 ]; then
            echo -e "${YELLOW}Python相关问题 ($PYTHON_ISSUES 个):${NC}"
            echo "  Linux:"
            echo "    1. 安装或升级Python: sudo apt install python3.13"
            echo "  macOS (推荐 Homebrew Python):"
            echo "    1. brew install python@3.13"
            echo "    2. python3.13 -m venv venv"
            echo "    3. source venv/bin/activate"
            echo "  Windows:"
            echo "    1. 下载安装: https://www.python.org/downloads/"
            echo "  2. 验证版本: python3 --version"
            echo ""
        fi
        
        if [ $OLLAMA_ISSUES -gt 0 ]; then
            echo -e "${YELLOW}Ollama相关问题 ($OLLAMA_ISSUES 个):${NC}"
            echo "  1. 安装Ollama: curl -fsSL https://ollama.com/install.sh | sh"
            echo "  2. 启动服务: ollama serve"
            echo "  3. 下载模型: ollama pull qwen2.5-coder:7b"
            echo "  4. 验证服务: curl http://localhost:11434/api/tags"
            echo ""
        fi
        
        if [ $DEPENDENCY_ISSUES -gt 0 ]; then
            echo -e "${YELLOW}Python依赖相关问题 ($DEPENDENCY_ISSUES 个):${NC}"
            echo "  1. 自动安装: ./scripts/install_deps.sh  # 推荐"
            echo "  2. 手动安装: pip install -r requirements.txt"
            echo "  3. 检查虚拟环境: 确保在虚拟环境中运行"
            echo "  4. 确保 Python 版本为 3.13+ (推荐 Python 3.13.13)"
            echo ""
        fi
        
        if [ $NETWORK_ISSUES -gt 0 ]; then
            echo -e "${YELLOW}网络相关问题 ($NETWORK_ISSUES 个):${NC}"
            echo "  1. 检查网络连接: ping google.com"
            echo "  2. 检查防火墙设置"
            echo "  3. 配置代理（如果需要）: export HTTP_PROXY=..."
            echo "  4. 重启Ollama服务: ollama serve"
            echo ""
        fi
        
        echo "解决所有问题后，重新运行此脚本验证："
        echo "  ./scripts/check_prereqs.sh"
        
        return 1
    fi
}

# 运行主函数
main