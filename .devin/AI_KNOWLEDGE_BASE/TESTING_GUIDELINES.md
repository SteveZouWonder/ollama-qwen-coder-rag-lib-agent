# 测试指南

## 🎯 强制测试要求（MUST - 必须遵守）

### 代码修改后必须添加测试（强制）

**任何代码修改都必须伴随相应的测试代码**：

#### 新功能开发
- ✅ **必须**为新功能编写完整的单元测试
- ✅ **必须**测试正常功能和边界条件
- ✅ **必须**测试异常处理和错误情况
- ✅ **必须**确保测试覆盖率≥95%

#### Bug修复
- ✅ **必须**为修复编写复现测试
- ✅ **必须**验证修复效果
- ✅ **必须**确保没有副作用
- ✅ **必须**测试相关功能（回归测试）

#### 代码重构
- ✅ **必须**更新现有测试以适应新代码
- ✅ **必须**确保测试覆盖率不降低
- ✅ **必须**验证重构不影响功能

#### 依赖变更
- ✅ **必须**测试新依赖的兼容性
- ✅ **必须**测试依赖变更的影响范围

### 覆盖率要求（强制）

- **最低覆盖率**: 95%
- **关键路径**: 100%覆盖
- **核心模块**: 98%+覆盖
- **新功能**: 95%+覆盖

**低于95%覆盖率的代码将被拒绝交付。**

### 测试质量要求（强制）

- ✅ 测试必须独立且可重复
- ✅ 测试必须有清晰的命名和描述
- ✅ 测试必须使用合理的Mock
- ✅ 测试必须覆盖边界条件
- ✅ 测试必须有适当的fixture管理

**违反以上强制要求的测试将被拒绝交付。**

## 🧪 测试类型

### 单元测试 (Unit Tests)
**目的**: 测试单个函数或方法的行为
**特点**: 快速、独立、可重复
**工具**: pytest, unittest.mock

**示例**:
```python
def test_rag_engine_query():
    """测试RAG引擎查询功能"""
    engine = RAGEngine()
    engine.add_documents(["test document"])
    result = engine.query("test question")
    assert "test" in result.lower()
```

### 集成测试 (Integration Tests)
**目的**: 测试模块间交互和数据流
**特点**: 较慢、需要真实依赖、测试组件协作

**示例**:
```python
def test_rag_with_web_search():
    """测试RAG与网络搜索集成"""
    engine = RAGEngine()
    result = engine.query_with_web_search("latest Python version")
    assert result
```

### 端到端测试 (End-to-End Tests)
**目的**: 测试完整工作流和用户场景
**特点**: 最慢、模拟真实用户操作

**示例**:
```python
def test_complete_workflow():
    """测试完整工作流：添加文档→查询→验证"""
    # 添加文档
    add_result = query_interface.process_command("/add doc.pdf")
    assert "成功" in add_result
    
    # 查询
    query_result = query_interface.process_command("/ask test question")
    assert query_result
```

## 🔧 测试隔离要求

### pytest Fixture使用

### 全局状态重置
```python
# conftest.py
@pytest.fixture(autouse=True)
def reset_all_states():
    """重置所有全局状态"""
    from agent_tools import set_rag_engine
    from agent_tools import reset_rag_engine
    
    # 保存原始状态
    original_engine = get_rag_engine()
    
    yield
    
    # 重置状态
    set_rag_engine(original_engine)
    reset_rag_engine()
```

### 模块级别fixture
```python
@pytest.fixture
def clean_rag_engine():
    """提供干净的RAG引擎"""
    engine = RAGEngine()
    yield engine
    # 清理
    engine.clear_index()
```

### 类级别fixture
```python
@pytest.fixture(scope="class")
def shared_resource():
    """类级别的共享资源"""
    resource = expensive_operation()
    yield resource
    release_resource(resource)
```

### 状态污染预防

### 避免全局变量
```python
# ❌ 不推荐
test_data = []

def test_1():
    test_data.append("data1")

def test_2():
    assert len(test_data) == 0  # 可能失败，test_1修改了全局状态

# ✅ 推荐
def test_1():
    data = ["data1"]
    assert len(data) == 1

def test_2():
    data = ["data2"]
    assert len(data) == 1
```

### 及时清理资源
```python
@pytest.fixture
def temp_file():
    """临时文件fixture"""
    import tempfile
    fd, path = tempfile.mkstemp()
    yield path
    # 清理
    os.close(fd)
    os.unlink(path)
```

## 🎭 Mock使用规范

### 何时使用Mock
- **外部依赖**: 网络请求、文件系统、数据库
- **性能优化**: 避免慢速操作
- **隔离测试**: 消除第三方影响
- **不可控因素**: 随机性、时间依赖

### Mock使用示例

### Mock函数
```python
from unittest.mock import patch, Mock

@patch('agent_tools.execute_command')
def test_with_mock_command(mock_execute):
    """Mock命令执行"""
    mock_execute.return_value "command output"
    result = execute_command("test command")
    assert result == "command output"
```

### Mock类
```python
def test_with_mock_class():
    """Mock类实例化"""
    from unittest.mock import MagicMock
    
    mock_engine = MagicMock()
    mock_engine.query.return_value = "test result"
    
    result = process_with_engine(mock_engine)
    assert result == "test result"
```

### Autospec使用
```python
@patch.object_path('module.Class', autospec=True)
def test_autospec(mock_class):
    """使用autospec保持接口一致性"""
    mock_class.method()  # 严格匹配实际接口
```

### 避免Mock过度使用
```python
# ❌ 不推荐: Mock一切
@patch('module.function1')
@patch('module.function2')  
@patch('module.function3')
def test_overmocked(f1, f2, f3):
    pass  # 难以理解真实行为

# ✅ 推荐: 只Mock外部依赖
@patch('requests.get')
def test_targeted(mock_get):
    mock_get.return_value = {"data": "test"}
    result = fetch_data()
    assert result
```

## 📊 覆盖率要求

### 覆盖率目标
- **最低覆盖率**: 95%
- **关键路径**: 100%覆盖
- **核心模块**: 98%+覆盖
- **新功能**: 95%+覆盖

### 检查覆盖率
```bash
# 检查特定模块覆盖率
python -m pytest tests/test_rag_engine.py --cov=rag_engine --cov-report=term-missing

# 检查整体覆盖率
python -m pytest tests/ --cov=src --cov-report=term-missing

# 生成HTML报告
python -m pytest tests/ --cov=src --cov-report=html
```

### 覆盖率策略
```python
# 测试边界条件
def test_boundary_conditions():
    """测试边界条件"""
    assert function_with_limit(max=0) == expected
    assert function_with_limit(max=100) == expected
    
# 测试异常处理
def test_exception_handling():
    """测试异常处理"""
    with pytest.raises(ValueError):
        function_that_raises_value_error()
    
# 测试空值
def test_empty_inputs():
    """测试空值输入"""
    assert process_data("") == default_result
```

## 🧪 测试编写规范

### 测试命名
```python
# 推荐: 描述性命名
def test_rag_engine_query_with_empty_database():
    """测试空数据库查询"""
    
def test_agent_execute_with_timeout():
    """测试Agent执行超时处理"""

# 不推荐: 模糊命名
def test_1():
    """测试功能1"""
```

### 测试结构
```python
class TestRAGEngine:
    """RAG引擎测试类"""
    
    def setup_method(self):
        """每个测试前执行"""
        self.engine = RAGEngine()
    
    def teardown_method(self):
        """每个测试后执行"""
        self.engine.clear_index()
    
    def test_query_with_documents(self):
        """测试有文档的查询"""
        # Arrange
        self.engine.add_documents(["test doc"])
        
        # Act
        result = self.engine.query("test")
        
        # Assert
        assert result is not None
```

### 参数化测试
```python
@pytest.mark.parametrize("input_data,expected", [
    ("doc1", True),
    ("doc2", True),
    ("", False)
])
def test_document_addition(input_data, expected):
    """参数化测试：文档添加"""
    engine = RAGEngine()
    result = engine.add_documents([input_data])
    assert result == expected or not input_data
```

## ⚠️ 常见测试陷阱

### 陷阱1: 测试顺序依赖
```python
# ❌ 不推荐: 测试有顺序依赖
test_1需要特定状态
def test_1():
    global state = "modified"

def test_2():
    assert state == "modified"  # 依赖test_1

# ✅ 推荐: 测试独立
def test_1():
    local_state = "modified"
    assert local_state == "modified"

def test_2():
    assert True  # 不依赖其他测试
```

### 陷阱2: Mock过度使用
```python
# ❌ 不推荐: Mock真实逻辑
@patch('rag_engine.RAGEngine.query')
def test_query_mocked(mock_query):
    mock_query.return_value = "fake result"
    engine = RAGEngine()
    result = engine.query("question")
    # 测试的是Mock，不是真实逻辑

# ✅ 推荐: 只Mock外部依赖
@patch('requests.post')
def test_query_real_logic(mock_post):
    mock_post.return_value = {"embedding": [0.1, 0.2]}
    engine = RAGEngine()
    result = engine.query("question")
    # 测试真实逻辑，只Mock网络请求
```

### 陷阱3: 异步测试问题
```python
# ✅ 推荐: 使用pytest-asyncio
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result == expected

# ✅ 推荐: 同步包装异步
def test_async_wrapper():
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(async_function())
    assert result == expected
```

### 陷阱4: 时区和时间依赖
```python
# ❌ 不推荐: 依赖当前时间
def test_date_logic():
    assert is_today(datetime.now())  # 可能失败

# ✅ 推荐: 使用固定时间
def test_date_logic():
    fixed_date = datetime(2024, 1, 1)
    assert is_fixed_date(fixed_date)
```

## 🚀 测试执行

### 运行特定测试
```bash
# 运行单个测试文件
python -m pytest tests/test_rag_engine.py

# 运行特定测试函数
python -m pytest tests/test_rag_engine.py::test_query

# 运行测试类
python -m pytest tests/test_rag_engine.py::TestRAGEngine
```

### 并行测试
```bash
# 使用pytest-xdist并行运行
python -m pytest tests/ -n auto

# 指定并行度
python -m pytest tests/ -n 4
```

### 失败测试重跑
```bash
# 只运行失败的测试
python -m pytest tests/ --lf

# 重运行失败的测试一次
python -m pytest tests/ --lf -x
```

### 停止在第一次失败
```bash
# 第一个失败后停止
python -m pytest tests/ -x

# 第N个失败后停止
python -m pytest tests/ -x --maxfail=3
```

## 📈 性能测试

### 性能测试框架
```python
import pytest
import time

def test_query_performance():
    """测试查询性能"""
    engine = RAGEngine()
    engine.add_documents(["test doc"])
    
    start = time.time()
    result = engine.query("test")
    elapsed = time.time() - start
    
    assert elapsed < 5.0  # 5秒内完成
```

### 内存泄漏测试
```python
import pytest
import gc

@pytest.mark.repeat(10)
def test_no_memory_leak():
    """重复测试检测内存泄漏"""
    engine = RAGEngine()
    for i in range(100):
        engine.add_documents([f"doc_{i}"])
    gc.collect()  # 强制垃圾回收
    # 内存应该稳定
```

## 🛠️ 测试调试

### 查看详细输出
```bash
# 显示详细输出
python -m pytest tests/test_rag_engine.py -v

# 显示print输出
python -m pytest tests/test_rag_engine.py -s

# 进入pdb调试
python -m pytest tests/test_rag_engine.py --pdb
```

### 只运行匹配的测试
```bash
# 运行名称匹配的测试
python -m pytest tests/ -k "query"

# 运行路径匹配的测试
python -m pytest tests/test_rag_engine.py -k "test_query"
```

### 显示测试时长
```bash
# 显示最慢的10个测试
python -m pytest tests/ --durations=10

# 按时长排序
python -m pytest tests/ --durations
```

## 📋 测试检查清单

### 功能测试
- [ ] 正常功能测试
- [ ] 边界条件测试
- [ ] 错误处理测试
- [ ] 兼容性测试

### 集成测试
- [ ] 模块间交互测试
- [ ] 数据流测试
- [ ] 状态管理测试
- [ ] 错误恢复测试

### 测试质量
- [ ] 测试独立性
- [ ] 测试可读性
- [ ] 测试可维护性
- [ ] Mock合理性

### 性能测试
- [ ] 响应时间测试
- [ ] 内存使用测试
- [ ] 并发测试
- [ ] 资源泄漏测试

遵循这些测试指南可以确保项目质量和稳定性。