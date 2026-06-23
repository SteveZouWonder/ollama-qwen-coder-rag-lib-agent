# 代码规范

## 🐍 Python代码风格

### 基本规范
- **PEP 8**: 遵循PEP 8代码风格指南
- **类型提示**: 重要函数必须添加类型提示
- **文档字符串**: 所有类和重要函数必须有docstring
- **命名约定**: 
  - 类名: PascalCase (如: `RAGEngine`)
  - 函数名: snake_case (如: `query_with_sources`)
  - 常量: UPPER_CASE (如: `MAX_HISTORY`)
  - 私有成员: 前缀下划线 (如: `_internal_var`)

### 导入顺序
```python
# 1. 标准库导入
import os
import sys
from pathlib import Path

# 2. 第三方库导入
import chromadb
from llama_index import VectorStoreIndex

# 3. 本地导入
from config import Config
from rag_engine import RAGEngine
```

### 字符串格式化
```python
# 推荐: f-string (Python 3.6+)
name = "World"
message = f"Hello {name}"

# 不推荐: % 或 .format
message = "Hello %s" % name
message = "Hello {}".format(name)
```

### 类型提示
```python
from typing import List, Dict, Optional, Any, Callable

def process_data(
    data: List[str],
    config: Dict[str, Any],
    callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """处理数据的函数"""
    pass
```

## 📝 文档字符串规范

### 函数文档字符串
```python
def search_files(keyword: str, path: str = ".", max_results: int = 10) -> List[str]:
    """
    在项目中搜索包含关键字的文件
    
    Args:
        keyword: 搜索关键字
        path: 搜索路径，默认为当前目录
        max_results: 最大结果数，默认10
    
    Returns:
        包含关键字的文件路径列表
        
    Examples:
        >>> search_files("import", "./src")
        ["./src/rag_engine.py", "./src/agent_tools.py"]
        
    Raises:
        FileNotFoundError: 如果搜索路径不存在
    """
    pass
```

### 类文档字符串
```python
class RAGEngine:
    """
    RAG知识库引擎 - 文档检索和语义搜索
    
    该引擎负责管理文档的向量化存储、语义检索和结果排序。
    支持多种文档格式，具备缓存机制和快照功能。
    
    Attributes:
        query_engine: LlamaIndex查询引擎
        vector_store: 向量存储
        embed_model: 嵌入模型
    
    Examples:
        >>> engine = RAGEngine()
        >>> engine.add_documents(["document.pdf"])
        >>> results = engine.query("搜索问题")
    """
    pass
```

## � 依赖管理规范

### 依赖添加要求
- **Python版本兼容性**: 新依赖必须兼容 Python 3.13.13
- **版本选择**: 使用兼容Python 3.13.13的最新稳定版本
- **版本指定**: 使用 >= 或 ~= 指定最低版本，避免硬编码特定版本

### 依赖添加流程
```python
# 1. 检查Python版本兼容性
# 查看官方文档或PyPI页面确认Python版本要求

# 2. 添加到requirements.txt
# 使用>=指定最低版本
package_name>=1.0.0  # 推荐
# 或使用~=指定兼容版本
package_name~=1.0.0   # 推荐
# 避免使用==硬编码特定版本（特殊情况除外）
package_name==1.2.3   # 不推荐，除非有特殊原因

# 3. 更新依赖安装脚本
# 在scripts/install_deps.sh中添加包名映射和导入验证
# 特别处理导入名称和包名的映射

# 4. 更新依赖检查脚本
# 在scripts/check_prereqs.sh和verify_deps.sh中添加验证逻辑
# 确保包能正确导入

# 5. 测试验证
# 运行依赖检查脚本验证安装
# 运行相关测试确保兼容性
```

### 依赖管理示例
```python
# ❌ 不推荐: 硬编码版本，可能不兼容Python 3.13
package_name==1.2.3

# ❌ 不推荐: 未指定最低版本
package_name

# ✅ 推荐: 指定最低版本
package_name>=1.0.0

# ✅ 推荐: 指定兼容版本范围
package_name~=1.0.0
```

### 特殊依赖处理
- **OCR相关**: Python 3.13推荐使用Tesseract而非PaddleOCR
- **Git操作**: 使用系统git命令而非gitpython库
- **可选依赖**: 在注释中标注"可选"和"何时需要"

### 脚本更新要求
添加新依赖时必须：
1. **更新requirements.txt**: 添加依赖和版本要求
2. **更新install_deps.sh**: 添加包名映射和导入验证
3. **更新verify_deps.sh**: 添加模块导入验证
4. **更新check_prereqs.sh**: 添加依赖检查逻辑
5. **测试脚本**: 运行验证脚本确保正确识别

## �🔧 错误处理规范

### 异常处理原则
- 具体异常捕获，避免过于宽泛的except
- 提供有用的错误信息
- 记录详细的错误日志
- 优雅降级，不要让程序崩溃

### 异常处理示例
```python
import logging

logger = logging.getLogger(__name__)

def process_document(file_path: str) -> bool:
    """处理文档"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # 处理逻辑
        return True
    except FileNotFoundError:
        logger.error(f"文件不存在: {file_path}")
        return False
    except UnicodeDecodeError:
        logger.error(f"文件编码错误: {file_path}")
        return False
    except Exception as e:
        logger.error(f"处理文档失败: {file_path}, 错误: {e}")
        return False
```

### 用户友好错误信息
```python
def execute_command(command: str) -> str:
    """执行命令"""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            return f"[错误] 命令执行失败: {result.stderr}"
        return result.stdout
    except Exception as e:
        return f"[错误] 执行异常: {str(e)}"
```

## 🗂️ 日志记录规范

### 日志级别使用
- **DEBUG**: 调试信息，开发时使用
- **INFO**: 一般信息，记录关键流程
- **WARNING**: 警告信息，不影响功能但需要注意
- **ERROR**: 错误信息，功能受影响
- **CRITICAL**: 严重错误，系统可能无法继续

### 日志格式
```python
import logging

logger = logging.getLogger(__name__)

logger.debug("调试信息")
logger.info("一般信息")  
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误")
```

### 结构化日志
```python
logger.info("处理文档", extra={
    "file_path": file_path,
    "file_size": file_size,
    "processing_time": time_taken
})
```

## 🔄 状态管理规范

### 全局状态使用原则
- **最小化**: 尽量减少全局状态
- **封装**: 通过函数访问，不直接操作
- **重置**: 使用后必须重置
- **文档**: 全局状态必须文档化

### 全局状态示例
```python
# 推荐: 封装访问
def get_rag_engine():
    """获取RAG引擎实例"""
    global _rag_engine
    return _rag_engine

def set_rag_engine(engine):
    """设置RAG引擎实例"""
    global _rag_engine
    _rag_engine = engine

# 不推荐: 直接操作
_rag_engine = new_engine
```

### 状态重置要求
```python
# 在conftest.py中的fixture
@pytest.fixture(autouse=True)
def reset_rag_engine():
    """重置RAG引擎状态"""
    from agent_tools import set_rag_engine
    # 清理或重置状态
    set_rag_engine(None)
    yield
    # 清理操作
```

### 缓存一致性
```python
# 缓存失效策略
def update_document(file_path: str):
    """更新文档时，使相关缓存失效"""
    # 1. 更新向量索引
    rag_engine.update_document(file_path)
    # 2. 清除相关缓存
    clear_search_cache(file_path)
    # 3. 更新快照
    snapshot_manager.update_snapshot()
```

## ⚡ 异步编程规范

### 异步函数设计
```python
import asyncio
from typing import List

async def search_web(query: str, max_results: int = 10) -> List[dict]:
    """
    异步网络搜索
    
    Args:
        query: 搜索查询
        max_results: 最大结果数
        
    Returns:
        搜索结果列表
    """
    try:
        # 异步操作
        results = await perform_search(query, max_results)
        return results
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return []
```

### 事件循环管理
```python
# 在同步上下文中调用异步函数
def sync_search(query: str) -> List[dict]:
    """同步包装异步搜索"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(search_web(query))
        return results
    finally:
        loop.close()
```

### 资源释放
```python
async def process_with_timeout(func, timeout: int = 30):
    """带超时的异步处理"""
    try:
        result = await asyncio.wait_for(func(), timeout=timeout)
        return result
    except asyncio.TimeoutError:
        logger.warning(f"操作超时: {timeout}s")
        return None
    finally:
        # 清理资源
        await cleanup_resources()
```

## 🧪 测试编写规范

### 单元测试结构
```python
import pytest
from unittest.mock import Mock, patch

def test_rag_engine_query():
    """测试RAG引擎查询功能"""
    # Arrange
    engine = RAGEngine()
    test_documents = ["doc1.pdf", "doc2.pdf"]
    engine.add_documents(test_documents)
    
    # Act
    results = engine.query("测试问题")
    
    # Assert
    assert len(results) > 0
    assert all('content' in result for result in results)
```

### Mock使用规范
```python
from unittest.mock import Mock, MagicMock, patch

@patch('agent_tools.execute_command')
def test_command_execution(mock_execute):
    """测试命令执行，mock实际的命令调用"""
    # Arrange
    mock_execute.return_value "command output"
    
    # Act
    result = execute_command("echo test")
    
    # Assert
    assert result == "command output"
    mock_execute.assert_called_once()
```

### 测试数据管理
```python
# 使用fixture提供测试数据
@pytest.fixture
def sample_documents():
    """提供示例文档"""
    return [
        "content of document 1",
        "content of document 2"
    ]

# 测试类使用fixture
class TestDocumentProcessor:
    def test_process_single_document(self):
        """测试单个文档处理"""
        doc = "test content"
        result = process_document(doc)
        assert result is True
```

### 覆盖率要求
- **最低覆盖率**: 95%
- **关键路径**: 100%覆盖
- **边界条件**: 必须覆盖

## 🔐 安全编程规范

### 输入验证
```python
def safe_path_join(base_path: str, user_path: str) -> str:
    """安全的路径拼接，防止目录遍历攻击"""
    base = Path(base_path).resolve()
    user = Path(user_path).resolve()
    
    if not str(user).startswith(str(base)):
        raise ValueError("不允许访问父目录")
    
    return str(user)
```

### 敏感信息保护
```python
import logging

def log_safe(message: str, sensitive_data: dict = None):
    """安全的日志记录，避免记录敏感信息"""
    if sensitive_data:
        # 移除敏感字段
        safe_data = {k: v for k, v in sensitive_data.items() 
                    if not is_sensitive(k)}
        logger.info(message, extra=safe_data)
    else:
        logger.info(message)

def is_sensitive(key: str) -> bool:
    """判断是否为敏感字段"""
    sensitive_keys = ['password', 'token', 'key', 'secret']
    return any(s in key.lower() for s in sensitive_keys)
```

### 命令注入防护
```python
import re

def is_safe_command(command: str) -> bool:
    """检查命令安全性"""
    dangerous_patterns = [
        r'rm\s+-rf\s+/',
        r'mkfs\.',
        r'curl\s+.*\|\s*sh',
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return False
    
    return True
```

## 📦 代码组织规范

### 文件命名
- 模块文件: snake_case (如: `rag_engine.py`)
- 类文件: snake_case (如: `agent_orchestrator.py`)
- 包目录: snake_case (如: `command_recommender/`)

### 类组织
```python
# 标准类组织
class MyClass:
    """类文档字符串"""
    
    def __init__(self, param1: str, param2: int):
        """初始化方法"""
        self.param1 = param1
        self.param2 = param2
        self._internal_state = None
    
    def public_method(self) -> str:
        """公共方法"""
        return "result"
    
    def _private_method(self) -> str:
        """私有方法"""
        return "private result"
    
    @property
    def computed_property(self) -> str:
        """属性装饰器"""
        return f"{self.param1}-{self.param2}"
```

### 常量定义
```python
# 模块级常量
MAX_HISTORY = 100
DEFAULT_TIMEOUT = 300
SUPPORTED_FORMATS = ["pdf", "txt", "md"]

# 类级常量
class Config:
    """配置类"""
    CHUNK_SIZE = 1024
    TOP_K = 5
    SIMILARITY_CUTOFF = 0.7
```

## 🎯 性能优化规范

### 列表和字典操作
```python
# 推荐: 列表推导式
result = [process_item(item) for item in large_list if condition(item)]

# 推荐: 集合去重
unique_items = set(items)

# 推荐: 生成器处理大文件
def process_large_file(file_path):
    with open(file_path) as f:
        for line in f:
            yield process_line(line)
```

### 资源管理
```python
# 推荐: 使用with语句管理资源
with open(file_path, 'r') as f:
    content = f.read()
    # 自动关闭文件

# 推荐: contextlib资源管理
from contextlib import contextmanager

@contextmanager
def resource_manager():
    resource = acquire_resource()
    try:
        yield resource
    finally:
        release_resource(resource)
```

遵循这些代码规范可以确保代码质量、可维护性和一致性。