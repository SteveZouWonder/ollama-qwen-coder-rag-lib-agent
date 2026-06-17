#!/bin/bash
# 测试运行脚本 - 避免测试隔离问题
# 由于某些测试在完整套件中存在相互影响，使用分批运行

set -e

echo "======================================"
echo "  测试套件 - 分批运行"
echo "======================================"

# 激活虚拟环境
source venv/bin/activate

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
       -v --tb=short --no-cov

# 第二批：UI和查询接口
echo ""
echo "【2/4】运行UI和查询接口测试..."
pytest tests/test_query_interface_*.py \
       tests/test_desktop_app.py \
       -v --tb=short --no-cov

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
       -v --tb=short --no-cov

# 第四批：RAG引擎、React引擎和其他
echo ""
echo "【4/4】运行RAG引擎、React引擎和其他测试..."
pytest tests/test_rag_engine.py \
       tests/test_react_engine.py \
       tests/test_session_manager.py \
       tests/test_system_prompt.py \
       tests/test_web_search.py \
       -v --tb=short --no-cov

echo ""
echo "======================================"
echo "  所有批次测试完成"
echo "======================================"
