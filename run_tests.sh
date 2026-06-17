#!/bin/bash
# 测试运行脚本 - 提供多种运行方式
# 由于某些测试在完整套件中存在相互影响，提供多种测试策略

set -e

MODE=${1:-"batch"}

echo "======================================"
echo "  测试套件 - 多模式运行"
echo "======================================"

# 激活虚拟环境
source venv/bin/activate

if [ "$MODE" = "parallel" ]; then
    echo ""
    echo "【并行模式】使用pytest-xdist运行所有测试..."
    echo "  每个测试进程完全独立，避免状态污染"
    pytest tests/ -n auto --no-cov --tb=short -q -k "not integration and not tesseract"
    
elif [ "$MODE" = "batch" ]; then
    echo ""
    echo "【分批模式】将测试分为4个批次运行..."
    
    # 第一批：核心模块和工具
    echo ""
    echo "【1/4】运行核心模块和工具测试..."
    pytest tests/multi_agent/ \
           tests/test_agent_tools_*.py \
           tests/test_chat_history.py \
           tests/test_code_analyzer.py \
           tests/test_config.py \
           tests/test_content_security.py \
           tests/test_database_tools.py \
           --tb=short --no-cov -q
    
    # 第二批：UI和查询接口
    echo ""
    echo "【2/4】运行UI和查询接口测试..."
    pytest tests/test_query_interface_*.py \
           tests/test_desktop_app.py \
           --tb=short --no-cov -q
    
    # 第三批：文档处理和知识管理
    echo ""
    echo "【3/4】运行文档处理和知识管理测试..."
    pytest tests/test_document_loader.py \
           tests/test_file_validator.py \
           tests/test_knowledge_*.py \
           tests/test_ocr_base.py \
           tests/test_ocr_cache.py \
           tests/test_ocr_image_extractor.py \
           tests/test_ocr_preprocessor.py \
           --tb=short --no-cov -q -k "not integration"
    
    # 第四批：RAG引擎、React引擎和其他
    echo ""
    echo "【4/4】运行RAG引擎、React引擎和其他测试..."
    pytest tests/test_rag_engine.py \
           tests/test_react_engine.py \
           tests/test_session_manager.py \
           tests/test_web_search.py \
           --tb=short --no-cov -q
    
    echo ""
    echo "======================================"
    echo "  所有批次测试完成 ✅"
    echo "======================================"

elif [ "$MODE" = "coverage" ]; then
    echo ""
    echo "【覆盖率模式】运行测试并生成覆盖率报告（串行）..."
    pytest tests/ -k "not integration and not tesseract" --cov-report=html --cov-report=term -q

else
    echo ""
    echo "❌ 未知模式: $MODE"
    echo ""
    echo "使用方法:"
    echo "  ./run_tests.sh batch       # 分批运行（推荐）"
    echo "  ./run_tests.sh parallel    # 并行运行（推荐）"
    echo "  ./run_tests.sh coverage    # 生成覆盖率报告"
    echo ""
    exit 1
fi

echo ""
echo "======================================"
echo "  测试完成 ✅"
echo "======================================"
