# 常见问题规避

## 🧪 状态管理陷阱

### 陷阱1: 全局状态污染
**问题**: 全局变量在测试间相互影响
```python
# ❌ 不推荐
_test_data = []

def test_1():
    global _test_data
    _test_data.append("data1")

def test_2():
    assert len(_test_data) == 0  # 可能失败，test_1修改了全局状态
```

**解决方案**:
```python
# ✅ 推荐: 使用fixture管理状态
@pytest.fixture
def test_data():
    """每个测试独立的数据"""
    return ["data1"]

def test_1(test_data):
    data = test_data
    assert len(data) == 1

def test_2(test_data):
    data = test_data
    assert len(data) == 1  # 独立状态
```

### 陷阱2: 缓存不一致
**问题**: 缓存未及时更新导致数据不一致
```python
# ❌ 不推荐
cache = {}

def process_data(key, value):
    if key not in cache:
        result = expensive_operation(key)
        cache[key] = result
    return cache[key]  # 缓存可能过期

def update_data(key, new_value):
    # 忘记清除缓存，但可能遗漏
    if key in cache:
        del cache[key]
```

**解决方案**:
```python
# ✅ 推荐: 统一缓存管理
class CacheManager:
    def __init__(self):
        self._cache = {}
        self._ttl = {}
    
    def get(self, key):
        if self._is_expired(key):
            del self._cache[key]
            return None
        return self._cache.get(key)
    
    def set(self, key, value, ttl=3600):
        self._cache[key] = value
        self._ttl[key] = time.time() + ttl
    
    def clear(self, pattern=None):
        if pattern:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
        else:
            self._cache.clear()
```

### 陷阱3: Agent状态残留
**问题**: Agent在多任务执行中状态污染
```python
# ❌ 不推荐
agent = CodeAgent()
agent.state = "task1"

def test_task1():
    agent.execute("task1")  # 修改agent.state

def test_task2():
    assert agent.state == "initial"  # 可能失败，被task1修改
```

**解决方案**:
```python
# ✅ 推荐: 无状态Agent设计
class CodeAgent:
    def execute(self, task: str) -> AgentResult:
        # 不存储状态，每次任务独立
        return AgentResult(
            task_id=hash(task),
            result=process_task(task)
        )
```

## 🧪 测试隔离陷阱

### 陷阱1: Mock污染
**问题**: Mock配置在测试间污染
```python
# ❌ 不推荐
import unittest.mock as mock

# 全局Mock，影响所有测试
mock.patch('module.function', return_value="mocked")

def test_1():
    # 使用mocked函数
    assert module.function() == "mocked"

def test_2():
    # 测试2也受影响，不是真实测试
    assert module.function() == "mocked"  # 不正确
```

**解决方案**:
```python
# ✅ 推荐: 局部Mock，及时恢复
def test_1():
    with mock.patch('module.function', return_value="mocked"):
        assert module.function() == "mocked"
    # 自动恢复真实函数

def test_2():
    assert module.function() != "mocked"  # 真实测试
```

### 陷阱2: 文件系统残留
**问题**: 测试文件未清理导致后续测试失败
```python
# ❌ 不推荐
def test_file_operations():
    with open("test_file.txt", "w") as f:
        f.write("test data")
    # 文件未清理，可能影响其他测试
```

**解决方案**:
```python
# ✅ 推荐: 使用fixture自动清理
@pytest.fixture
def temp_file():
    """临时文件fixture"""
    import tempfile
    fd, path = tempfile.mkstemp()
    yield path
    # 自动清理
    os.close(fd)
    os.unlink(path)

def test_file_operations(temp_file):
    with open(temp_file, "w") as f:
        f.write("test data")
    # 文件自动清理
```

### 陷阱3: 数据库状态残留
**问题**: 测试数据库数据污染
```python
# ❌ 不推荐
def test_database_insert():
    db.insert({"id": 1, "data": "test"})
    # 数据未清理

def test_database_query():
    result = db.query("SELECT * FROM table")
    assert len(result) == 0  # 可能失败，test_insert残留数据
```

**解决方案**:
```python
# ✅ 推荐: 使用事务和清理
@pytest.fixture
def clean_database():
    """干净的数据库fixture"""
    db.begin_transaction()
    yield db
    # 回滚事务
    db.rollback()

def test_database_insert(clean_database):
    db.insert({"id": 1, "data": "test"})
    # 自动回滚，不影响其他测试

def test_database_query(clean_database):
    result = db.query("SELECT * FROM table")
    assert len(result) == 0  # 干净的数据库
```

## ⚡ 性能陷阱

### 陷阱1: 内存泄漏
**问题**: 资源未释放导致内存持续增长
```python
# ❌ 不推荐
def process_large_data():
    results = []
    for item in large_dataset:
        result = expensive_operation(item)
        results.append(result)
    # results持续增长，可能内存溢出
    return results
```

**解决方案**:
```python
# ✅ 推荐: 使用生成器和及时清理
def process_large_data():
    def generator():
        for item in large_dataset:
            result = expensive_operation(item)
            yield result
    # 生成器内存友好
    
    # 或使用批量处理
    batch_size = 1000
    for i in range(0, len(large_dataset), batch_size):
        batch = large_dataset[i:i+batch_size]
        process_batch(batch)
        # 处理完批次，及时释放内存
```

### 陷阱2: 连接池耗尽
**问题**: 数据库或HTTP连接未释放
```python
# ❌ 不推荐
def query_database():
    connection = get_connection()
    result = connection.query("SELECT * FROM large_table")
    # 连接未释放
    return result
```

**解决方案**:
```python
# ✅ 推荐: 使用上下文管理器
def query_database():
    with get_connection() as connection:
        result = connection.query("SELECT * FROM large_table")
        return result
    # 自动释放连接

# 或使用连接池
from contextlib import contextmanager

@contextmanager
def connection_context():
    conn = connection_pool.get_connection()
    try:
        yield conn
    finally:
        connection_pool.release_connection(conn)
```

### 陷阱3: 阻塞IO
**问题**: 同步阻塞IO导致性能差
```python
# ❌ 不推荐
def fetch_all_urls(urls):
    results = []
    for url in urls:
        response = requests.get(url)  # 阻塞，逐个请求
        results.append(response)
    return results  # 总时间 = 所有请求时间之和
```

**解决方案**:
```python
# ✅ 推荐: 异步并发请求
import asyncio
import aiohttp

async def fetch_all_urls(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_url(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
    return results  # 总时间 ≈ 最慢的请求时间
```

## 🔐 安全陷阱

### 陷阱1: 命令注入
**问题**: 用户输入直接执行命令导致命令注入
```python
# ❌ 不推荐
def execute_user_command(command):
    result = subprocess.run(command, shell=True)  # 危险！
    return result
```

**解决方案**:
```python
# ✅ 推荐: 命令安全检查
def execute_user_command(command: command):
    if not is_safe_command(command):
        raise ValueError("不安全的命令")
    result = subprocess.run(command, shell=True, capture_output=True)
    return result

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

### 陷阱2: 路径遍历
**问题**: 用户输入路径遍历访问任意文件
```python
# ❌ 不推荐
def read_user_file(file_path: str):
    with open(file_path, 'r') as f:
        return f.read()  # 危险！
```

**解决方案**:
```python
# ✅ 推荐: 路径安全验证
def read_user_file(file_path: str):
    safe_path = validate_path(file_path)
    with open(safe_path, 'r') as f:
        return f.read()

def validate_path(file_path: str) -> str:
    """验证路径安全性"""
    base = Path("/safe/directory").resolve()
    try:
        user_path = Path(file_path).resolve()
    except:
        raise ValueError("无效路径")
    
    if not str(user_path).startswith(str(base)):
        raise ValueError("不允许访问目录外部路径")
    
    return str(user_path)
```

### 陷阱3: 敏感信息泄露
**问题**: 日志或错误信息包含敏感数据
```python
# ❌ 不推荐
def handle_user_data(user_data):
    try:
        process(user_data)
    except Exception as e:
        logger.error(f"处理失败: {user_data['password']}")  # 泄露密码！
```

**解决方案**:
```python
# ✅ 推荐: 敏感信息过滤
def handle_user_data(user_data):
    try:
        process(user_data)
    except Exception as e:
        logger.error(f"处理失败: {mask_sensitive_data(user_data)}")

def mask_sensitive_data(data: dict) -> dict:
    """过滤敏感字段"""
    sensitive_keys = ['password', 'token', 'key', 'secret', 'api_key']
    safe_data = data.copy()
    for key in sensitive_keys:
        if key in safe_data:
            safe_data[key] = "***"
    return safe_data
```

## 🔧 集成陷阱

### 陷阱1: 循环依赖
**问题**: 模块间相互依赖导致导入错误
```python
# module_a.py
from module_b import function_b

# module_b.py  
from module_a import function_a  # 循环依赖
```

**解决方案**:
```python
# ✅ 推荐: 依赖注入
# module_a.py
def process_a(b_function):
    """module_a依赖module_b，但不直接导入"""
    return b_function()

# module_b.py
def process_b(a_function):
    """module_b依赖module_a，但不直接导入"""
    return a_function()

# 通过外部协调器注入依赖
def process():
    from module_a import process_a
    from module_b import process_b
    
    return process_a(process_b)
```

### 陷阱2: 接口变更破坏
**问题**: 接口变更导致依赖模块失败
```python
# ❌ 不推荐: 破坏性接口变更
def process_data(data: List[str]) -> str:
    return " ".join(data)

# 更改接口
def process_data(data: List[str], separator: str) -> str:  # 破坏兼容
    return separator.join(data)
```

**解决方案**:
```python
# ✅ 推荐: 接口版本化
class DataProcessorV1:
    def process(self, data: List[str]) -> str:
        return " ".join(data)

class DataProcessorV2:
    def __init__(self):
        self.v1_processor = DataProcessorV1()
    
    def process(self, data: List[str], separator: str = None) -> str:
        if separator is None:
            # 向后兼容：使用v1接口
            return self.v1_processor.process(data)
        else:
            return separator.join(data)
```

### 陷阱3: 配置漂移
**问题**: 环境变量或配置文件变更导致行为不一致
```python
# ❌ 不推荐: 硬编码配置
API_KEY = "hardcoded_key"  # 配置漂移

def fetch_data():
    return fetch_with_key(API_KEY)
```

**解决方案**:
```python
# ✅ 推荐: 配置中心化管理
class Config:
    API_KEY = os.getenv("API_KEY", "default_key")
    DATABASE_URL = os.getenv("DATABASE_URL", "localhost:5432")
    
    @classmethod
    def load_from_file(cls, config_path: str):
        with open(config_path) as f:
            config_data = json.load(f)
            cls.API_KEY = config_data.get("API_KEY", cls.API_KEY)
```

## 🎯 项目特定陷阱

### 陷阱1: RAG索引状态污染
**问题**: ChromaDB索引在测试间相互影响
```python
# ❌ 不推荐: 共享RAG引擎实例
_rag_engine = RAGEngine()  # 全局共享

def test_1():
    _rag_engine.add_documents(["doc1"])
    
def test_2():
    results = _rag_engine.query("test")  # 可能包含doc1的结果
```

**解决方案**:
```python
# ✅ 推荐: 每个测试使用独立引擎
@pytest.fixture
def rag_engine():
    """独立的RAG引擎fixture"""
    engine = RAGEngine()
    yield engine
    engine.clear_index()  # 清理索引
```

### 陷阱2: Agent工具状态残留
**问题: agent_tools中的_rag_engine状态在测试间残留
```python
# ❌ 不推荐
from agent_tools import set_rag_engine

def test_1():
    set_rag_engine(engine1)  # 修改全局状态

def test_2():
    # test_2可能使用test_1设置的engine1
    pass
```

**解决方案**:
```python
# ✅ 推荐: 使用fixture注入状态
@pytest.fixture
def agent_tools_with_rag():
    """注入测试用的RAG引擎"""
    test_engine = RAGEngine()
    set_rag_engine(test_engine)
    yield
    set_rag_engine(None)  # 重置
```

### 陷阱3: 命令推荐历史影响
**问题**: 推荐系统历史数据污染测试结果
```python
# ❌ 不推荐
def test_recommendation():
    result = command_recommender.get_recommendations()
    # 可能受到之前测试历史的影响
    assert len(result) > 0
```

**解决方案**:
```python
# ✅ 推荐: 使用测试专用的推荐器实例
@pytest.fixture
def test_recommender():
    """测试专用的推荐器实例"""
    recommender = CommandRecommender(mode="test")
    recommender.clear_history()  # 清除历史
    yield recommender
```

### 陷阱4: 网络搜索缓存干扰
**问题: 网络搜索缓存影响测试一致性
```python
# ❌ 不推荐
def test_web_search():
    result = web_search("test query")
    # 缓存结果可能与真实结果不同
```

**解决方案**:
```python
# ✅ 推荐: 测试时禁用缓存或使用Mock
@pytest.fixture
def web_search_no_cache():
    """禁用缓存的网络搜索"""
    return lambda query: web_search(query, use_cache=False)

def test_web_search(web_search_no_cache):
    result = web_search_no_cache("test query")
    # 真实网络请求，不使用缓存
    assert "test" in result.lower()
```

## 🔍 问题诊断方法

### 状态污染诊断
```python
def debug_state_pollution():
    """诊断状态污染"""
    import gc
    
    # 检查全局变量
    global_vars = globals()
    print(f"全局变量: {[k for k in global_vars if not k.startswith('_')]}")
    
    # 检查单例状态
    singletons = [RAGEngine, AgentOrchestrator]
    for cls in singletons:
        instances = [obj for obj in gc.get_objects() if isinstance(obj, cls)]
        print(f"{cls.__name__}实例数量: {len(instances)}")
    
    # 检查缓存
    print(f"缓存大小: {len(cache._cache)}")
    
    # 强制垃圾回收
    gc.collect()
```

### Mock泄漏诊断
```python
def check_mock_leakage():
    """检查Mock泄漏"""
    from unittest import mock
    
    # 检查未恢复的patch
    assert not any(
        isinstance(obj, mock._patch)
        for obj in gc.get_objects()
    )
```

### 连接泄漏诊断
```python
def check_connection_leak():
    """检查连接泄漏"""
    import psutil
    process = psutil.Process()
    connections = process.connections()
    print(f"活跃连接数: {len(connections)}")
```

## 📋 修改前检查清单

### 状态管理检查
- [ ] 确认是否修改全局状态
- [ ] 确认状态使用后重置
- [ ] 确认缓存一致性处理
- [ ] 确认异步资源释放

### 测试隔离检查
- [ ] 确认测试独立运行
- [ ] 确认使用fixture管理状态
- [ ] 确认Mock合理使用
- [ ] 确认测试清理完善

### 性能检查
- [ ] 确认无内存泄漏
- [ ] 确认连接正确释放
- [ ] 确认阻塞IO使用异步
- [ ] 确认缓存使用合理

### 安全检查
- [ ] 确认输入验证
- [ ] 确认路径安全
- [ ] 确认敏感信息保护
- [ ] 确认命令安全

遵循这些规避指南可以避免常见陷阱，提高代码质量和项目稳定性。