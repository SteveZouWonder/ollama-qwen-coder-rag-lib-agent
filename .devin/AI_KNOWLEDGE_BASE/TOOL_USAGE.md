# 工具使用指南

## 🛠️ 可用工具清单

### 文件操作工具
```python
# 读取文件内容
def read_file(file_path: str) -> str:
    """读取文件内容"""
    pass

# 写入文件内容
def write_file(file_path: str, content: str) -> bool:
    """写入文件内容"""
    pass

# 列出目录内容
def list_directory(path: str = ".") -> List[str]:
    """列出目录内容"""
    pass

# 创建目录
def create_directory(path: str) -> bool:
    """创建目录"""
    pass

# 删除文件
def delete_file(file_path: str) -> bool:
    """删除文件"""
    pass
```

### 命令执行工具
```python
# 执行命令
def execute_command(command: str, working_dir: str = ".", timeout: int = 300) -> str:
    """执行命令"""
    pass

# 安全命令执行
def safe_execute(command: str, confirm: bool = False) -> str:
    """安全执行命令（带确认）"""
    pass
```

### RAG检索工具
```python
# 查询知识库
def query_knowledge_base(question: str, top_k: int = 5) -> str:
    """查询知识库"""
    pass

# 添加文档到知识库
def add_to_knowledge_base(file_paths: List[str]) -> str:
    """添加文档到知识库"""
    pass

# 查询带来源
def query_with_sources(question: str) -> Dict:
    """查询并返回来源信息"""
    pass
```

### 网络搜索工具
```python
# 网络搜索
def web_search(query: str, max_results: int = 5, use_cache: bool = True) -> str:
    """网络搜索"""
    pass

# 网页内容提取
def web_content_extract(url: str, use_cache: bool = True) -> str:
    """提取网页内容"""
    pass
```

### 代码分析工具
```python
# AST搜索
def ast_search(file_path: str, search_type: str, pattern: str) -> List[str]:
    """AST搜索"""
    pass

# 代码质量检查
def code_quality_check(file_path: str) -> Dict:
    """代码质量检查"""
    pass
```

### Git操作工具
```python
# Git分析
def git_analyze(repo_path: str = ".", analysis_type: str = "history") -> str:
    """Git历史分析"""
    pass

# Git提交信息生成
def git_commit_gen(repo_path: str = ".") -> str:
    """生成提交信息"""
    pass
```

## 🎯 工具使用规范

### 安全工具确认流程

### 危险命令识别
```python
# 自动检测危险命令
from agent_tools import CommandSafetyChecker

command = "rm -rf /"
safety = CommandSafetyChecker.analyze(command)
if not safety['is_safe']:
    print(f"警告: {safety['reason']}")
    print(f"建议: {safety['suggestion']}")
    # 需要用户确认
```

### 用户确认机制
```python
# 非安全命令需要用户确认
def execute_with_confirmation(command: str):
    safety = CommandSafetyChecker.analyze(command)
    if not safety['is_safe'] and not auto_confirm:
        if not ask_user_confirmation(f"确认执行: {command}?"):
            return "用户取消"
    return execute_command(command)
```

### 参数验证
```python
def validate_params(tool_name: str, params: Dict) -> bool:
    """验证工具参数"""
    if tool_name == "read_file":
        if not params.get("file_path"):
            return False
        if not Path(params["file_path"]).exists():
            return False
    return True
```

## 🔧 工具组合模式

### 模式1: 文件读写+命令执行
```python
def analyze_code_file(file_path: str) -> str:
    """分析代码文件"""
    # 读取文件
    code = read_file(file_path)
    
    # 执行分析
    result = execute_command(f"python -m pylint {file_path}")
    
    # 返回分析结果
    return f"代码分析:\n{result}"
```

### 模式2: RAG检索+Agent推理
```python
def answer_with_knowledge(question: str) -> str:
    """使用知识库回答问题"""
    # 先从知识库检索
    kb_answer = query_knowledge_base(question)
    
    # 如果知识库结果不足，使用Agent推理
    if not kb_answer or len(kb_answer) < 100:
        agent_answer = agent_reasoning(question)
        return f"知识库: {kb_answer}\n\n推理: {agent_answer}"
    
    return kb_answer
```

### 模式3: 网络搜索+知识库整合
```python
def comprehensive_search(query: str) -> str:
    """综合搜索：网络+知识库"""
    # 网络搜索
    web_results = web_search(query)
    
    # 知识库搜索
    kb_results = query_knowledge_base(query)
    
    # 整合结果
    integrated = integrate_results(web_results, kb_results)
    return integrated
```

### 模式4: 文件批量处理
```python
def batch_process_files(directory: str, operation: str) -> str:
    """批量处理文件"""
    files = list_directory(directory)
    results = []
    
    for file_path in files:
        if operation == "analyze":
            result = code_quality_check(file_path)
        elif operation == "format":
            result = execute_command(f"black {file_path}")
        results.append(result)
    
    return "\n".join(results)
```

## ⚠️ 工具限制说明

### 网络访问限制
- 需要网络连接
- 有请求频率限制
- 部分网站可能拒绝爬取
- 结果有缓存，可能不是最新的

### 文件系统限制
- 只能访问项目目录下文件
- 大文件读取可能超时
- 需要适当的文件权限
- 避免符号链接循环

### 资源使用限制
- 单次操作超时：300秒
- 内存使用限制：取决于系统
- 并发操作限制：避免过多并发
- 缓存空间限制：定期清理

### 命令执行限制
- 危险命令需要用户确认
- 有命令长度限制
- 环境变量继承有限制
- 输出大小限制

## 📝 工具调用示例

### 文件操作示例
```python
# 读取配置文件
config_content = read_file("config.json")
config_data = json.loads(config_content)

# 写入日志
log_message = f"[{time.now()}] Operation completed\n"
write_file("app.log", log_message)

# 列出所有Python文件
py_files = list_directory("./src", pattern="*.py")
```

### 命令执行示例
```python
# 运行测试
test_result = execute_command("python -m pytest tests/ -v")

# Git操作
git_status = execute_command("git status")
git_log = execute_command("git log --oneline -10")

# Docker操作
docker_ps = execute_command("docker ps")
```

### RAG检索示例
```python
# 简单查询
answer = query_knowledge_base("如何使用RAG引擎?")

# 带来源查询
result = query_with_sources("项目架构是什么?")
for source in result['sources']:
    print(f"来源: {source['file']}")
    print(f"内容: {source['content']}")
```

### 网络搜索示例
```python
# 搜索信息
results = web_search("Python 3.13 新特性", max_results=5)

# 提取网页
content = web_content_extract("https://example.com")
```

### Agent工具示例
```python
# Agent推理
answer = agent_reasoning("如何优化这段代码?")

# 多Agent协作
result = agent_orchestrator.process(
    "分析并优化这段代码",
    mode="collaborative"
)
```

## 🔍 工具调试

### 工具调用日志
```python
# 启用详细日志
import logging
logging.getLogger('agent_tools').setLevel(logging.DEBUG)

# 查看工具调用
execute_command("echo test")  # 会输出详细调用信息
```

### 工具性能分析
```python
import time

def profile_tool_call(tool_func, *args, **kwargs):
    """分析工具调用性能"""
    start = time.time()
    result = tool_func(*args, **kwargs)
    elapsed = time.time() - start
    print(f"工具调用耗时: {elapsed:.2f}s")
    return result
```

### 工具错误诊断
```python
def debug_tool_error(tool_name: str, params: Dict):
    """诊断工具错误"""
    try:
        result = registry.execute(tool_name, params)
        return result
    except Exception as e:
        print(f"工具错误: {tool_name}")
        print(f"参数: {params}")
        print(f"错误: {e}")
        # 检查参数有效性
        if not validate_params(tool_name, params):
            print("参数验证失败")
        raise
```

## 🚀 工具性能优化

### 缓存工具结果
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_web_search(query: str) -> str:
    """带缓存的网络搜索"""
    return web_search(query, use_cache=False)  # 禁用内置缓存，使用lru_cache
```

### 批量工具调用
```python
def batch_web_search(queries: List[str]) -> Dict[str, str]:
    """批量网络搜索"""
    results = {}
    for query in queries:
        results[query] = web_search(query)
    return results
```

### 异步工具调用
```python
async def async_tool_call(tool_func, *args, **kwargs):
    """异步工具调用包装"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, tool_func, *args, **kwargs)
    return result
```

## 🔐 工具安全注意事项

### 路径安全
```python
def safe_file_operation(file_path: str, operation: str):
    """安全文件操作"""
    # 验证路径
    safe_path = validate_path(file_path)
    
    # 检查文件权限
    if not os.access(safe_path, os.R_OK):
        raise PermissionError(f"无读取权限: {safe_path}")
    
    # 执行操作
    if operation == "read":
        return read_file(safe_path)
    elif operation == "write":
        return write_file(safe_path, content)
```

### 命令安全
```python
def safe_command_execution(command: str):
    """安全命令执行"""
    # 安全检查
    safety = CommandSafetyChecker.analyze(command)
    if not safety['is_safe']:
        raise ValueError(f"不安全的命令: {safety['reason']}")
    
    # 执行
    result = execute_command(command)
    return result
```

### 数据安全
```python
def safe_data_logging(data: dict):
    """安全数据日志"""
    # 过滤敏感信息
    safe_data = mask_sensitive_data(data)
    
    # 记录日志
    logger.info(f"操作数据: {safe_data}")
```

## 📋 工具使用检查清单

### 调用前检查
- [ ] 确认工具参数完整
- [ ] 确认权限满足
- [ ] 确认资源可用
- [ ] 确认操作安全

### 调用中监控
- [ ] 监控执行状态
- [ ] 捕获异常错误
- [ ] 记录关键日志
- [ ] 处理超时情况

### 调用后验证
- [ ] 验证结果正确性
- [ ] 清理临时资源
- [ ] 更新相关状态
- [ ] 记录操作日志

## 🎓 工具最佳实践

### 1. 始终验证参数
```python
# ✅ 推荐
def process_file(file_path: str):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    # 处理逻辑
```

### 2. 适当的错误处理
```python
# ✅ 推荐
def risky_operation():
    try:
        result = execute_command("risky_command")
        return result
    except subprocess.TimeoutExpired:
        logger.error("命令执行超时")
        return None
    except Exception as e:
        logger.error(f"命令执行失败: {e}")
        return None
```

### 3. 资源及时清理
```python
# ✅ 推荐
def process_temp_data():
    temp_file = tempfile.mktemp()
    try:
        # 使用临时文件
        write_file(temp_file, data)
        result = process_file(temp_file)
        return result
    finally:
        # 确保清理
        if os.path.exists(temp_file):
            os.unlink(temp_file)
```

### 4. 使用缓存优化性能
```python
# ✅ 推荐
@lru_cache(maxsize=50)
def expensive_operation(data: str) -> str:
    """昂贵操作使用缓存"""
    return complex_processing(data)
```

遵循这些工具使用指南可以确保工具调用的安全性、正确性和高效性。