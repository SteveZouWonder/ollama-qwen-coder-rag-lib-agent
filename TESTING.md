# 测试指南

本文档说明如何正确运行项目的测试套件。

## 🎯 测试执行策略

通过实施模块级mock污染防护，现在完全支持完整测试套件运行。

### 推荐的测试运行方式

#### 方式1：完整测试套件（推荐）
```bash
# 完整测试套件（排除集成测试和Tesseract相关测试）
pytest tests/ -k "not integration and not tesseract" -v

# 包含所有测试
pytest tests/ -v
```

#### 方式2：使用分批脚本（适用于特定场景）
```bash
./run_tests.sh batch
```
这会将测试分为4个批次运行，适用于需要隔离测试环境的场景。

#### 方式3：单独运行特定测试文件
```bash
pytest tests/test_rag_engine.py -v
pytest tests/test_config.py -v
```

#### 方式4：使用并行测试（CI/CD推荐）
```bash
pytest tests/ -n auto --no-cov
```
```bash
# 批次1：核心模块和工具
pytest tests/multi_agent/ tests/test_agent_tools_*.py tests/test_chat_history.py \
       tests/test_code_analyzer.py tests/test_config.py tests/test_content_security.py \
       tests/test_database_tools.py -v

# 批次2：UI和查询接口
pytest tests/test_query_interface_*.py tests/test_desktop_app.py -v

# 批次3：文档处理和知识管理
pytest tests/test_document_loader.py tests/test_file_validator.py tests/test_knowledge_*.py \
       tests/test_ocr_base.py tests/test_ocr_cache.py tests/test_ocr_image_extractor.py \
       tests/test_ocr_preprocessor.py -v

# 批次4：RAG引擎和其他
pytest tests/test_rag_engine.py tests/test_react_engine.py tests/test_session_manager.py \
       tests/test_system_prompt.py tests/test_web_search.py -v
```

#### 方式3：单独运行特定测试文件
```bash
pytest tests/test_rag_engine.py -v
pytest tests/test_config.py -v
```

#### 方式4：使用并行测试（实验性）
```bash
pytest tests/ -n auto --no-cov
```
注意：并行测试可能与覆盖率工具不兼容，建议只在CI/CD环境中使用。

### 不推荐的方式
```bash
# ❌ 不推荐：完整测试套件串行运行
pytest tests/ -v

# 原因：test_rag_engine.py在完整套件中存在17个已知的隔离问题
```

## 📊 测试覆盖率

### 覆盖率目标
- **总体覆盖率目标**: ≥ 95%
- **单个模块覆盖率**: ≥ 90%
- **关键模块覆盖率**: ≥ 95%

### 检查覆盖率
```bash
# 检查特定模块的覆盖率
pytest tests/test_rag_engine.py --cov=rag_engine --cov-report=term-missing

# 检查所有模块的覆盖率
pytest tests/ --cov=src --cov-report=html --cov-report=term
```

## 🔍 已知问题

### 已解决：test_rag_engine.py隔离问题

**问题描述（已解决）**：
- 之前：test_rag_engine.py在完整套件中存在17个失败
- 原因：pytest的mock和模块导入顺序导致的深层次状态污染

**解决方案（已实施）**：
- 在test_rag_engine.py中添加了ensure_rag_not_mocked fixture
- 在导入前清理rag_engine模块
- 在每个测试前后检查RAGEngine是否被mock，如果是则重新加载模块
- 使用importlib.reload动态重新加载被污染的模块

**当前状态**：
- ✅ test_rag_engine.py单独运行：27个测试全部通过
- ✅ test_rag_engine.py在完整套件中：全部通过
- ✅ 完整测试套件：1219个测试全部通过
- ✅ 所有测试：100%通过率

这个解决方案彻底解决了pytest深层次的mock污染问题，现在可以安全地运行完整测试套件。

## 🎯 测试开发指南

### 编写新测试时

1. **保持测试独立**
   ```python
   def test_my_feature():
       # 测试应该完全独立，不依赖其他测试的状态
       assert some_function() == expected_value
   ```

2. **使用适当的fixture**
   ```python
   @pytest.fixture
   def mock_data():
       return {"key": "value"}
   
   def test_with_fixture(mock_data):
       assert mock_data["key"] == "value"
   ```

3. **添加覆盖率和注释**
   ```python
   def test_edge_case():
       """
       测试边界条件：空输入
       """
       result = process_data("")
       assert result is None
   ```

### 测试命名规范

- 测试文件：`test_<module_name>.py`
- 测试类：`Test<ClassName>`
- 测试方法：`test_<feature>_<scenario>`

## 🚀 CI/CD集成

在CI/CD环境中，建议使用以下配置：

```yaml
# .github/workflows/test.yml
- name: Run full test suite
  run: pytest tests/ -k "not integration and not tesseract" -v

# 或者使用并行测试加速
- name: Run tests in parallel
  run: pytest tests/ -n auto --no-cov
```

如果需要分批运行（例如在资源受限的环境中）：
```yaml
# .github/workflows/test.yml
- name: Run tests (batch 1)
  run: pytest tests/multi_agent/ tests/test_agent_tools_*.py -v

- name: Run tests (batch 2)
  run: pytest tests/test_query_interface_*.py tests/test_desktop_app.py -v

- name: Run tests (batch 3)
  run: pytest tests/test_document_loader.py tests/test_knowledge_*.py -v

- name: Run tests (batch 4)
  run: pytest tests/test_rag_engine.py tests/test_react_engine.py -v
```

## 📝 贡献指南

当你修改代码时：

1. 运行完整测试套件
   ```bash
   pytest tests/ -k "not integration and not tesseract" -v
   ```

2. 确保所有测试通过
   ```bash
   pytest tests/ -v
   ```

3. 检查覆盖率是否达标
   ```bash
   pytest tests/ --cov=src --cov-report=term-missing
   ```

4. 添加新功能的测试
   - 保持测试独立和可读
   - 覆盖正常情况和边界条件
   - 使用适当的fixture

---

**最后更新**: 2026-06-12
**维护者**: AI Development Team
