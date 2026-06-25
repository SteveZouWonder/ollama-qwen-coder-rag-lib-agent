"""
pytest配置文件 - 全局测试设置
防止测试中触发实际的弹窗和系统调用
"""
import subprocess
import os
import tempfile
import shutil
import sys
import importlib
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
import warnings

# 忽略 pymupdf 的 Swig 类型警告（库的问题）
warnings.filterwarnings("ignore", category=DeprecationWarning, message="builtin type.*Swig.*")

# 添加项目根目录和src目录到Python路径，支持模块导入
# 项目根目录使 `from src.X import ...` 形式的导入可用
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
# src目录使 `from X import ...` 形式的直接导入可用
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def pytest_configure(config):
    """注册自定义 pytest markers，确保 --strict-markers 时不报错。"""
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "ocr: marks tests as OCR-related tests")


@pytest.fixture(autouse=True, scope="function")
def prevent_popups():
    """
    全局fixture：防止所有测试中触发实际弹窗
    
    scope="function" 确保每个测试都有独立的mock状态
    """
    with patch('subprocess.run') as mock_run:
        with patch('subprocess.Popen') as mock_popen:
            # 设置默认返回值，模拟成功的系统调用
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            mock_popen.return_value = Mock()
            
            yield


@pytest.fixture(autouse=True, scope="function")
def setup_settings_mock():
    """
    全局fixture：自动 mock Settings 以避免 LlamaIndex 类型检查问题
    
    scope="function" 确保每个测试都有独立的Settings mock状态
    """
    with patch('rag_engine.Settings') as mock_settings_class:
        mock_settings = MagicMock()
        mock_settings.llm = MagicMock()
        mock_settings.embed_model = MagicMock()
        mock_settings.node_parser = MagicMock()
        mock_settings_class.return_value = mock_settings
        
        yield


@pytest.fixture(autouse=True, scope="function")
def isolate_file_metadata(tmp_path_factory):
    """全局fixture：将文件元数据全局单例隔离到临时目录。

    RAGEngine 入库时会通过 get_global_metadata_manager() 登记文件元数据；
    若不隔离，使用 MagicMock 文档的测试会把伪造路径写入真实的
    .devin/file_metadata/metadata.json，污染用户数据。本 fixture 在每个
    测试前后将全局单例重置为临时目录，测试间互不影响、也不触碰真实文件。
    """
    try:
        import file_metadata as fm
    except ImportError:
        yield
        return

    tmp_dir = tmp_path_factory.mktemp("file_metadata")
    saved = getattr(fm, "_global_metadata_manager", None)
    fm._global_metadata_manager = fm.FileMetadataManager(storage_path=str(tmp_dir))
    try:
        yield
    finally:
        fm._global_metadata_manager = saved


@pytest.fixture(autouse=True, scope="function")
def isolate_knowledge_graph(tmp_path_factory):
    """全局fixture：将知识图谱全局单例隔离到临时目录。

    KnowledgeGraphBuilder 现在会自动持久化到 .devin/knowledge/graph.json，
    若不隔离，测试构建/清空图谱会读写真实文件、污染用户数据，且测试间共享
    持久化状态会相互影响。本 fixture 把全局 builder/query 单例重置为临时
    路径，并在测试结束后恢复。
    """
    try:
        import knowledge_graph.graph_builder as gb
        import knowledge_graph.graph_query as gq
    except ImportError:
        yield
        return

    tmp_dir = tmp_path_factory.mktemp("knowledge_graph")
    saved_builder = getattr(gb, "_graph_builder", None)
    saved_query = getattr(gq, "_graph_query", None)
    saved_override = getattr(gb, "_DEFAULT_PERSIST_PATH_OVERRIDE", None)

    # 重定向默认持久化路径：覆盖单例与“直接 KnowledgeGraphBuilder()”两类构造，
    # 确保任何测试都写入临时目录、不触碰真实 .devin/knowledge/graph.json。
    gb.set_default_persist_path(str(tmp_dir / "graph.json"))
    gb._graph_builder = gb.KnowledgeGraphBuilder(
        persist_path=str(tmp_dir / "graph.json")
    )
    gq._graph_query = None  # 下次 get_graph_query() 会基于新 builder 重建
    try:
        yield
    finally:
        gb.set_default_persist_path(saved_override)
        gb._graph_builder = saved_builder
        gq._graph_query = saved_query


@pytest.fixture
def clean_env():
    """
    清理测试环境的fixture（function scope）
    
    为每个测试提供一个干净的环境：
    1. 临时环境变量清理
    2. 临时目录创建和清理
    3. 确保测试之间不相互影响
    """
    # 保存当前环境变量
    original_env = os.environ.copy()
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    
    yield {
        'temp_dir': temp_dir,
        'original_env': original_env
    }
    
    # 清理：恢复环境变量
    os.environ.clear()
    os.environ.update(original_env)
    
    # 清理临时目录
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture(scope="function")
def temp_dir():
    """
    创建临时目录的fixture（function scope）
    """
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    # 清理临时目录
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


@pytest.fixture(scope="function")  
def mock_rag_engine():
    """
    Mock RAG engine fixture for agent tools tests
    """
    engine = MagicMock()
    engine.query_tool.return_value = "[Mock] 知识库查询结果"
    engine.add_document_tool.return_value = "[Mock] 文档已添加"
    engine.get_stats_tool.return_value = "[Mock] 统计信息"
    return engine


@pytest.fixture(autouse=True, scope="function")
def reset_module_state():
    """
    自动清理模块级别的全局状态
    
    某些模块可能存在全局变量或单例，这个fixture在每个测试后重置它们
    """
    yield
    
    # 重置query_interface模块的进度状态
    if 'query_interface' in sys.modules:
        module = sys.modules['query_interface']
        if hasattr(module, '_progress_state'):
            module._progress_state = {
                'last_line_length': 0,
                'important_phases': {"executing", "observed", "blocked", "rejected", "final"},
                'current_thinking_dots': 0
            }
    
    # 重置query_interface中的全局rag_engine状态
    if 'query_interface' in sys.modules:
        module = sys.modules['query_interface']
        if hasattr(module, 'rag_engine'):
            module.rag_engine = None
    
    # 重置agent_tools中的全局rag_engine状态
    if 'agent_tools' in sys.modules:
        module = sys.modules['agent_tools']
        if hasattr(module, '_rag_engine'):
            module._rag_engine = None