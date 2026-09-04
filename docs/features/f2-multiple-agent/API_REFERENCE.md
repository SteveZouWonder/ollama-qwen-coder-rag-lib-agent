# 多Agent系统API参考文档

## 📋 文档信息

- **文档版本**: v1.0
- **创建日期**: 2026-06-10
- **关联文档**: DESIGN.md, IMPLEMENTATION_GUIDE.md, DEVELOPMENT_GUIDE.md
- **API版本**: v1.0.0

---

## 📚 目录

1. [数据类型API](#数据类型api)
2. [核心组件API](#核心组件api)
3. [Agent API](#agent-api)
4. [协作机制API](#协作机制api)
5. [配置管理API](#配置管理api)
6. [异常处理](#异常处理)

---

## 数据类型API

### AgentTask

任务定义类，用于描述需要Agent执行的任务。

```python
@dataclass
class AgentTask:
    task_id: str                          # 任务唯一标识符
    task_type: str                        # 任务类型
    description: str                      # 任务描述
    required_capabilities: List[str]      # 所需能力列表
    input_data: Dict[str, Any]            # 输入数据
    dependencies: List[str] = []          # 依赖任务ID列表
    priority: int = 5                     # 优先级 (1-10)
    timeout: int = 300                    # 超时时间（秒）
    status: TaskStatus = PENDING          # 任务状态
    metadata: Dict[str, Any] = {}         # 元数据
    created_at: datetime = None           # 创建时间
    assigned_agent: Optional[str] = None  # 分配的Agent ID
    started_at: Optional[datetime] = None # 开始时间
    completed_at: Optional[datetime] = None # 完成时间
```

**方法**:
- `to_dict() -> Dict`: 转换为字典格式
- `from_dict(data: Dict) -> AgentTask`: 从字典创建实例

**示例**:

```python
from agents.agent_types import AgentTask

task = AgentTask(
    task_id="task_001",
    task_type="code_generation",
    description="实现用户登录功能",
    required_capabilities=["code_generation", "file_operations"],
    input_data={"requirements": "用户名密码登录"}
)
```

---

### AgentResult

Agent执行结果类。

```python
@dataclass
class AgentResult:
    task_id: str                # 任务ID
    agent_id: str              # 执行Agent的ID
    success: bool              # 是否成功
    output: str                # 输出结果
    metadata: Dict[str, Any]   # 元数据
    execution_time: float      # 执行时间（秒）
    error_message: str = ""    # 错误信息
    timestamp: datetime = None # 时间戳
```

**方法**:
- `to_dict() -> Dict`: 转换为字典格式

---

### AgentMessage

Agent间通信消息类。

```python
@dataclass
class AgentMessage:
    from_agent: str                  # 发送者Agent ID
    to_agent: str                    # 接收者Agent ID
    message_type: str                # 消息类型
    content: Dict[str, Any]          # 消息内容
    timestamp: datetime = None       # 时间戳
    message_id: str = ""             # 消息ID
```

**方法**:
- `to_dict() -> Dict`: 转换为字典格式

---

### AgentConfig

Agent配置类。

```python
@dataclass
class AgentConfig:
    agent_id: str                   # Agent ID
    agent_type: AgentType           # Agent类型
    model: str                     # 使用的模型
    host: str                      # 模型服务地址
    capabilities: List[str]        # 能力列表
    specialized_tools: List[str]   # 专属工具列表
    max_iterations: int = 50        # 最大迭代次数
    timeout: int = 300             # 超时时间（秒）
    enabled: bool = True           # 是否启用
    config_data: Dict[str, Any] = {} # 额外配置数据
```

**方法**:
- `to_dict() -> Dict`: 转换为字典格式

---

### OrchestratorConfig

编排器配置类。

```python
@dataclass
class OrchestratorConfig:
    master_agent_config: AgentConfig              # Master Agent配置
    agent_configs: List[AgentConfig]             # 专业Agent配置列表
    default_collaboration_mode: CollaborationMode # 默认协作模式
    max_parallel_tasks: int = 5                  # 最大并行任务数
    task_timeout: int = 600                       # 任务超时时间
    enable_logging: bool = True                  # 是否启用日志
    log_level: str = "INFO"                       # 日志级别
    log_file: Optional[str] = None               # 日志文件路径
```

**方法**:
- `to_dict() -> Dict`: 转换为字典格式

---

### 枚举类型

#### CollaborationMode

协作模式枚举。

```python
class CollaborationMode(Enum):
    HIERARCHY = "hierarchy"      # 层级协作
    PARALLEL = "parallel"        # 并行协作
    SEQUENTIAL = "sequential"   # 顺序协作
    COMPETITIVE = "competitive" # 竞争协作
```

#### AgentType

Agent类型枚举。

```python
class AgentType(Enum):
    MASTER = "master"
    CODE = "code"
    RAG = "rag"
    TEST = "test"
    DOC = "doc"
    AUDIT = "audit"
```

#### TaskStatus

任务状态枚举。

```python
class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

#### AgentState

Agent状态枚举。

```python
class AgentState(Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"
```

---

## 核心组件API

### AgentRegistry

Agent注册中心，管理所有Agent实例。

#### 初始化

```python
registry = AgentRegistry()
```

#### 方法

##### register(agent: BaseAgent) -> bool

注册Agent。

**参数**:
- `agent`: Agent实例

**返回**:
- `bool`: 注册是否成功

**示例**:

```python
from agent_registry import AgentRegistry
from agents import BaseAgent

registry = AgentRegistry()
agent = BaseAgent(config)
success = registry.register(agent)
```

##### unregister(agent_id: str) -> bool

注销Agent。

**参数**:
- `agent_id`: Agent ID

**返回**:
- `bool`: 注销是否成功

##### get_agent(agent_id: str) -> Optional[BaseAgent]

获取Agent实例。

**参数**:
- `agent_id`: Agent ID

**返回**:
- `Optional[BaseAgent]`: Agent实例，如果不存在返回None

##### find_agents_by_capability(capability: str) -> List[BaseAgent]

根据能力查找Agent。

**参数**:
- `capability`: 能力名称

**返回**:
- `List[BaseAgent]`: 匹配的Agent列表

##### find_agents_by_type(agent_type: AgentType) -> List[BaseAgent]

根据类型查找Agent。

**参数**:
- `agent_type`: Agent类型

**返回**:
- `List[BaseAgent]`: 匹配的Agent列表

##### get_all_agents() -> List[BaseAgent]

获取所有Agent。

**返回**:
- `List[BaseAgent]`: 所有Agent列表

##### get_agent_count() -> int

获取Agent数量。

**返回**:
- `int`: Agent数量

##### get_all_capabilities() -> List[str]

获取所有能力列表。

**返回**:
- `List[str]`: 能力列表

##### get_statistics() -> Dict

获取注册中心统计信息。

**返回**:
- `Dict`: 统计信息字典

##### shutdown_all()

关闭所有Agent。

---

### MessageBus

Agent间通信消息总线。

#### 初始化

```python
message_bus = MessageBus(
    enable_persistence=False,    # 是否启用消息持久化
    persistence_file=None        # 持久化文件路径
)
```

#### 方法

##### subscribe(agent_id: str, callback: Callable[[AgentMessage], None])

Agent订阅消息。

**参数**:
- `agent_id`: Agent ID
- `callback`: 消息处理回调函数

**示例**:
```python
def message_handler(message: AgentMessage):
    print(f"Received: {message.content}")

message_bus.subscribe("agent1", message_handler)
```

##### unsubscribe(agent_id: str, callback: Callable)

取消订阅。

**参数**:
- `agent_id`: Agent ID
- `callback`: 要取消的回调函数

##### publish(message: AgentMessage)

发布消息（点对点）。

**参数**:
- `message`: 要发布的消息

##### send_direct(from_agent: str, to_agent: str, message_type: str, content: Dict) -> str

点对点发送消息。

**参数**:
- `from_agent`: 发送者Agent ID
- `to_agent`: 接收者Agent ID
- `message_type`: 消息类型
- `content`: 消息内容

**返回**:
- `str`: 消息ID

**示例**:
```python
message_id = message_bus.send_direct(
    from_agent="agent1",
    to_agent="agent2",
    message_type="task_update",
    content={"status": "completed"}
)
```

##### broadcast(from_agent: str, message_type: str, content: Dict)

广播消息给所有订阅者（除了发送者）。

**参数**:
- `from_agent`: 发送者Agent ID
- `message_type`: 消息类型
- `content`: 消息内容

##### start()

启动消息处理线程。

##### stop()

停止消息处理线程。

##### get_message_history(limit: int = 100) -> List[AgentMessage]

获取消息历史。

**参数**:
- `limit`: 返回的消息数量限制

**返回**:
- `List[AgentMessage]`: 消息历史

##### get_statistics() -> Dict

获取消息总线统计信息。

**返回**:
- `Dict`: 统计信息字典

##### clear_history()

清空消息历史。

---

### TaskDecomposer

任务分解器，将复杂任务分解为子任务。

#### 初始化

```python
decomposer = TaskDecomposer()
```

#### 方法

##### decompose(request: str, context: Dict = None) -> List[AgentTask]

分解复杂任务为子任务。

**参数**:
- `request`: 用户请求
- `context`: 上下文信息（可选）

**返回**:
- `List[AgentTask]`: 分解后的子任务列表

**示例**:
```python
request = "实现用户登录功能，编写测试，并生成文档"
tasks = decomposer.decompose(request)

for task in tasks:
    print(f"Task: {task.task_type}, Description: {task.description}")
```

##### detect_dependencies(tasks: List[AgentTask]) -> Dict[str, List[str]]

检测任务依赖关系。

**参数**:
- `tasks`: 任务列表

**返回**:
- `Dict[str, List[str]]`: 依赖关系映射

##### estimate_complexity(task: AgentTask) -> int

评估任务复杂度（1-10）。

**参数**:
- `task`: 要评估的任务

**返回**:
- `int`: 复杂度评分

##### optimize_task_order(tasks: List[AgentTask]) -> List[AgentTask]

优化任务执行顺序。

**参数**:
- `tasks`: 任务列表

**返回**:
- `List[AgentTask]`: 优化后的任务列表

---

### TaskScheduler

任务调度器，分配任务给合适的Agent。

#### 初始化

```python
scheduler = TaskScheduler(registry: AgentRegistry)
```

#### 方法

##### schedule(tasks: List[AgentTask], mode: CollaborationMode) -> Dict[str, BaseAgent]

根据协作模式调度任务。

**参数**:
- `tasks`: 任务列表
- `mode`: 协作模式

**返回**:
- `Dict[str, BaseAgent]`: 任务到Agent的映射

##### execute_task(task: AgentTask, agent: BaseAgent) -> AgentResult

执行单个任务。

**参数**:
- `task`: 要执行的任务
- `agent`: 执行任务的Agent

**返回**:
- `AgentResult`: 执行结果

---

### ResultIntegrator

结果整合器，合并多个Agent的执行结果。

#### 初始化

```python
integrator = ResultIntegrator()
```

#### 方法

##### integrate(results: List[AgentResult], strategy: str = "merge") -> Dict

整合多个Agent的结果。

**参数**:
- `results`: Agent结果列表
- `strategy`: 整合策略（"merge", "concatenate", "vote", "select_best"）

**返回**:
- `Dict`: 整合后的结果

**示例**:
```python
results = [result1, result2, result3]
integrated = integrator.integrate(results, strategy="merge")
print(integrated["output"])
```

---

## Agent API

### BaseAgent

Agent基类，所有专业Agent都应继承此类。

#### 初始化

```python
agent = BaseAgent(config: AgentConfig)
```

#### 方法

##### process_task(task: AgentTask) -> AgentResult

处理任务（子类必须实现）。

**参数**:
- `task`: 要处理的任务

**返回**:
- `AgentResult`: 处理结果

**注意**: 这是抽象方法，子类必须实现。

##### can_handle(task: AgentTask) -> bool

判断是否能处理该任务。

**参数**:
- `task`: 要检查的任务

**返回**:
- `bool`: 是否能处理

##### get_capability() -> List[str]

获取能力列表。

**返回**:
- `List[str]`: 能力列表

##### get_state() -> AgentState

获取Agent状态。

**返回**:
- `AgentState`: Agent状态

##### register_message_handler(message_type: str, handler: Callable[[AgentMessage], None])

注册消息处理器。

**参数**:
- `message_type`: 消息类型
- `handler`: 处理函数

##### handle_message(message: AgentMessage)

处理接收到的消息。

**参数**:
- `message`: 接收到的消息

##### execute_task(task: AgentTask) -> AgentResult

执行任务（带状态管理）。

**参数**:
- `task`: 要执行的任务

**返回**:
- `AgentResult`: 执行结果

##### stop()

停止Agent。

##### reset()

重置Agent状态。

##### get_task_history(limit: int = 10) -> List[AgentResult]

获取任务历史。

**参数**:
- `limit`: 返回的历史记录数量限制

**返回**:
- `List[AgentResult]`: 任务历史

##### get_status() -> Dict[str, Any]

获取Agent状态信息。

**返回**:
- `Dict`: 状态信息字典

---

### MasterAgent

主控Agent，负责任务分解和协调。

#### 初始化

```python
master_agent = MasterAgent(
    agent_id: str = "master",
    registry: Optional[AgentRegistry] = None
)
```

#### 方法

##### process_task(task: AgentTask) -> AgentResult

处理任务（MasterAgent的特殊实现）。

**参数**:
- `task`: 要处理的任务

**返回**:
- `AgentResult`: 处理结果

##### coordinate_agents(request: str, mode: CollaborationMode = CollaborationMode.SEQUENTIAL) -> str

协调多个Agent处理请求。

**参数**:
- `request`: 用户请求
- `mode`: 协作模式

**返回**:
- `str`: 协调结果

**示例**:
```python
result = master_agent.coordinate_agents(
    request="实现用户认证系统",
    mode=CollaborationMode.SEQUENTIAL
)
print(result)
```

---

### 专业Agent

#### CodeAgent

代码专家Agent。

**专长**:
- 代码生成与重构
- Bug诊断与修复
- 代码审查与优化

**专属能力**:
- code_generation
- code_refactoring
- bug_fixing
- code_review

#### RAGAgent

知识库专家Agent。

**专长**:
- 文档检索与查询
- 知识提取与总结
- 文献综述生成

**专属能力**:
- knowledge_retrieval
- document_analysis
- semantic_search

#### TestAgent

测试专家Agent。

**专长**:
- 测试用例生成
- 测试覆盖率分析
- 质量评估

**专属能力**:
- test_generation
- test_execution
- coverage_analysis

#### DocAgent

文档专家Agent。

**专长**:
- API文档生成
- 技术文档编写
- 用户指南制作

**专属能力**:
- documentation
- api_docs
- technical_writing

#### AuditAgent

审计专家Agent。

**专长**:
- 安全检查
- 合规性验证
- 性能审计

**专属能力**:
- security_audit
- compliance_check
- performance_audit

---

## 协作机制API

### AgentOrchestrator

Agent编排器，协调Agent间的交互。

#### 初始化

```python
orchestrator = AgentOrchestrator(config: OrchestratorConfig)
```

#### 方法

##### process_request(request: str, mode: CollaborationMode) -> str

处理用户请求。

**参数**:
- `request`: 用户请求
- `mode`: 协作模式

**返回**:
- `str`: 处理结果

##### get_status() -> Dict

获取系统状态。

**返回**:
- `Dict`: 系统状态信息

##### shutdown()

关闭编排器。

---

## 配置管理API

### MultiAgentConfigLoader

多Agent配置加载器。

#### 方法

##### load_config(config_path: Optional[str] = None) -> OrchestratorConfig

加载配置文件。

**参数**:
- `config_path`: 配置文件路径，如果为None则使用默认路径

**返回**:
- `OrchestratorConfig`: 编排器配置

**示例**:
```python
from agent_config import MultiAgentConfigLoader

# 使用默认配置
config = MultiAgentConfigLoader.load_config()

# 使用自定义配置
config = MultiAgentConfigLoader.load_config("path/to/config.json")
```

##### save_config(config: OrchestratorConfig, config_path: Optional[str] = None)

保存配置到文件。

**参数**:
- `config`: 要保存的配置
- `config_path`: 保存路径，如果为None则使用默认路径

**示例**:
```python
from agent_config import MultiAgentConfigLoader

config = MultiAgentConfigLoader.load_config()
# 修改配置...
MultiAgentConfigLoader.save_config(config, "path/to/config.json")
```

---

## 异常处理

### 自定义异常

#### AgentRegistryError

Agent注册中心异常。

```python
class AgentRegistryError(Exception):
    """Agent注册中心异常"""
    pass
```

#### MessageBusError

消息总线异常。

```python
class MessageBusError(Exception):
    """消息总线异常"""
    pass
```

#### TaskDecompositionError

任务分解异常。

```python
class TaskDecompositionError(Exception):
    """任务分解异常"""
    pass
```

#### TaskSchedulingError

任务调度异常。

```python
class TaskSchedulingError(Exception):
    """任务调度异常"""
    pass
```

#### AgentExecutionError

Agent执行异常。

```python
class AgentExecutionError(Exception):
    """Agent执行异常"""
    pass
```

### 异常处理示例

```python
from agent_registry import AgentRegistry, AgentRegistryError

try:
    registry = AgentRegistry()
    agent = get_agent_instance()
    success = registry.register(agent)
    
    if not success:
        raise AgentRegistryError("Failed to register agent")
        
except AgentRegistryError as e:
    print(f"Registration error: {e}")
    # 处理异常
except Exception as e:
    print(f"Unexpected error: {e}")
    # 处理其他异常
```

---

## 使用示例

### 完整工作流程示例

```python
from agent_config import MultiAgentConfigLoader
from agent_registry import AgentRegistry
from collaboration import MessageBus
from collaboration import TaskDecomposer
from master_agent import MasterAgent
from agents.agent_types import CollaborationMode

# 1. 加载配置
config = MultiAgentConfigLoader.load_config()

# 2. 初始化核心组件
registry = AgentRegistry()
message_bus = MessageBus()
message_bus.start()

decomposer = TaskDecomposer()

# 3. 创建Master Agent
master_agent = MasterAgent(registry=registry)

# 4. 注册Master Agent
registry.register(master_agent)

# 5. 处理用户请求
request = "实现用户登录功能，编写测试，并生成API文档"
result = master_agent.coordinate_agents(
    request=request,
    mode=CollaborationMode.SEQUENTIAL
)

print(result)

# 6. 清理资源
message_bus.stop()
registry.shutdown_all()
```

### 自定义Agent示例

```python
from agents import BaseAgent
from agents.agent_types import AgentTask, AgentResult, AgentConfig, AgentType


class CustomAgent(BaseAgent):
    """自定义Agent"""

    def process_task(self, task: AgentTask) -> AgentResult:
        """实现自定义任务处理逻辑"""
        try:
            # 处理任务
            result_output = f"Custom processing for: {task.description}"

            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=True,
                output=result_output,
                metadata={"custom_info": "additional data"},
                execution_time=0.5
            )

        except Exception as e:
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=False,
                output="",
                metadata={},
                execution_time=0,
                error_message=str(e)
            )


# 使用自定义Agent
config = AgentConfig(
    agent_id="custom_agent",
    agent_type=AgentType.CODE,
    model="qwen2.5-coder:7b",
    host="http://localhost:11434",
    capabilities=["custom_capability"],
    specialized_tools=[]
)

custom_agent = CustomAgent(config)
```

---

## 版本兼容性

### API版本历史

#### v1.0.0 (当前版本)
- 初始版本
- 基础多Agent功能
- 4种协作模式
- 5种专业Agent类型

### 弃用API

当前版本没有弃用的API。

### 计划变更

未来版本可能添加以下API：
- 分布式Agent支持
- Agent学习机制
- 高级调度策略

---

## 最佳实践

### 1. Agent注册

```python
# 好的做法
registry = AgentRegistry()
try:
    success = registry.register(agent)
    if not success:
        logger.warning(f"Agent {agent.agent_id} registration failed")
except Exception as e:
    logger.error(f"Error registering agent: {e}")
```

### 2. 消息处理

```python
# 好的做法 - 添加错误处理
def safe_message_handler(message: AgentMessage):
    try:
        # 处理消息
        process_message(message)
    except Exception as e:
        logger.error(f"Error processing message: {e}")

message_bus.subscribe(agent_id, safe_message_handler)
```

### 3. 任务执行

```python
# 好的做法 - 检查Agent状态
if agent.get_state() == AgentState.IDLE:
    result = agent.execute_task(task)
else:
    logger.warning(f"Agent {agent.agent_id} is not available")
```

### 4. 配置管理

```python
# 好的做法 - 使用默认配置作为回退
try:
    config = MultiAgentConfigLoader.load_config("custom_config.json")
except Exception as e:
    logger.warning(f"Failed to load custom config, using default: {e}")
    config = MultiAgentConfigLoader.load_config()
```

---

## 性能考虑

### 资源管理

1. **Agent池化**: 复用Agent实例，避免频繁创建销毁
2. **消息队列**: 使用消息队列避免阻塞
3. **异步处理**: 对耗时操作使用异步处理

### 并发控制

```python
# 控制并发任务数
orchestrator_config = OrchestratorConfig(
    # ...
    max_parallel_tasks=5  # 限制并发数
)
```

---

## 安全考虑

### 消息验证

```python
def secure_message_handler(message: AgentMessage):
    # 验证消息来源
    if message.from_agent not in trusted_agents:
        logger.warning(f"Untrusted message from {message.from_agent}")
        return
    
    # 验证消息内容
    if not validate_content(message.content):
        logger.warning(f"Invalid message content")
        return
    
    # 处理消息
    process_message(message)
```

### 权限控制

```python
def check_agent_permission(agent: BaseAgent, task: AgentTask) -> bool:
    """检查Agent是否有权限执行任务"""
    # 实现权限检查逻辑
    return True
```

---

## 调试支持

### 日志配置

```python
import logging

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Agent会自动使用配置的日志级别
```

### 状态监控

```python
# 定期检查Agent状态
def monitor_agents(registry: AgentRegistry):
    for agent in registry.get_all_agents():
        status = agent.get_status()
        print(f"Agent {agent.agent_id}: {status['state']}")
```

---

**API参考文档结束**
