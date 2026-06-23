# 开发流程

## 🎯 强制要求（MUST - 必须遵守）

### 1. 依赖管理要求（强制）
**引入新依赖时**：
- ✅ 必须使用兼容Python 3.13.13的最新稳定版本
- ✅ 必须更新requirements.txt（使用>=或~=指定版本）
- ✅ 必须更新依赖安装脚本（install_deps.sh）
- ✅ 必须更新依赖检查脚本（verify_deps.sh, check_prereqs.sh）
- ✅ 必须运行验证脚本确认正确识别

**详细规范**见 `CODE_STANDARDS.md` 中的依赖管理章节。

### 2. 测试要求（强制）
**修改代码后**：
- ✅ 必须为新代码编写单元测试
- ✅ 必须为修改的代码更新单元测试
- ✅ 必须确保测试覆盖率≥95%
- ✅ 必须测试正常情况和异常情况
- ✅ 必须测试边界条件

**详细规范**见 `TESTING_GUIDELINES.md`。

### 3. 文档要求（强制）
**完成项目需求后**：
- ✅ 必须更新README.md相关章节
- ✅ 必须更新或创建TUTORIAL.md相关教程
- ✅ 必须更新技术文档（如适用）
- ✅ 必须添加使用示例
- ✅ 必须更新API文档（如适用）

**违反以上强制要求的代码将被拒绝交付。**

## 🔄 标准开发流程

### 代码修改标准流程

#### 1. 问题分析阶段
```
理解需求 → 分析影响范围 → 识别依赖关系 → 评估风险
```

**具体步骤**:
- **理解用户需求**: 明确要实现的功能或要修复的问题
- **分析影响范围**: 确定哪些文件和模块会受影响
- **识别依赖关系**: 找出相关的依赖和交互
- **评估风险**: 识别潜在的问题和副作用
- **制定方案**: 设计修改方案，考虑回退方案

**注意事项**:
- 先读取相关文件理解现状
- 检查是否有相关测试
- 确认是否会影响其他功能
- 评估修改复杂度

#### 2. 方案设计阶段
```
设计修改方案 → 评估兼容性 → 制定测试计划 → 设计错误处理
```

**具体步骤**:
- **设计修改方案**: 详细描述如何实现
- **评估兼容性**: 确保向后兼容
- **制定测试计划**: 确定需要编写/修改的测试
- **设计错误处理**: 考虑各种错误情况
- **确认回退方案**: 如果失败如何回滚

**注意事项**:
- 保持接口稳定性
- 考虑配置兼容性
- 测试边界条件
- 设计优雅降级

#### 3. 代码实现阶段
```
先读后写 → 保持向后兼容 → 添加错误处理 → 遵循代码规范
```

**具体步骤**:
- **先读后写原则**: 先读取文件，再进行修改
- **保持向后兼容**: 不破坏现有接口和数据
- **添加错误处理**: 使用try-catch处理异常
- **遵循代码规范**: PEP 8、类型提示、文档字符串

**注意事项**:
- 每次修改前先读取文件
- 最小化修改范围
- 添加适当的日志
- 保持代码风格一致

#### 4. 测试验证阶段
```
编写单元测试 → 运行相关测试 → 检查覆盖率 → 验证功能
```

**具体步骤**:
- **编写单元测试**: 覆盖正常情况和边界情况
- **运行相关测试**: 运行受影响的测试套件
- **检查覆盖率**: 确保达到95%以上
- **验证功能**: 手动测试修改的功能

**注意事项**:
- 测试独立性和可重复性
- 使用fixture管理测试状态
- Mock外部依赖
- 测试异常处理

#### 5. 文档更新阶段
```
更新相关文档 → 添加使用示例 → 更新变更日志
```

**具体步骤**:
- **更新相关文档**: 修改受影响的文档
- **添加使用示例**: 提供新的使用示例
- **更新变更日志**: 记录重要变更

**注意事项**:
- 文档与代码保持同步
- 示例可以实际运行
- 变更日志格式一致

## 🚀 新功能开发流程

### 功能开发标准流程
```
需求分析 → 设计方案 → 实现核心功能 → 编写测试 → 集成测试 → 文档编写
```

#### 1. 需求分析
- 明确功能需求
- 确定技术方案
- 评估实现复杂度
- 识别潜在风险

#### 2. 设计方案
- 设计API接口
- 设计数据结构
- 设计交互流程
- 确定测试策略

#### 3. 实现核心功能
- 创建新模块/文件
- 实现核心逻辑
- 添加错误处理
- 集成到现有系统

#### 4. 编写测试
- 单元测试
- 集成测试
- 边界测试
- 异常测试

#### 5. 集成测试
- 与现有模块集成
- 测试交互流程
- 验证兼容性

#### 6. 文档编写
- 功能文档
- API文档
- 使用示例

## 🐛 Bug修复流程

### Bug修复标准流程
```
问题重现 → 根因分析 → 设计修复方案 → 修复代码 → 测试验证
```

#### 1. 问题重现
- 获取详细的错误信息
- 理解复现步骤
- 确定问题影响范围

#### 2. 根因分析
- 分析错误堆栈
- 定位问题代码
- 确定根本原因

#### 3. 设计修复方案
- 设计最小化修复
- 考虑副作用
- 确定测试策略

#### 4. 修复代码
- 修改问题代码
- 添加错误处理
- 添加防护措施

#### 5. 测试验证
- 编写复现测试
- 验证修复效果
- 确保没有副作用

## 🔍 代码审查流程

### 审查检查清单

#### 功能审查
- [ ] 功能是否按需求实现
- [ ] 边界条件是否处理
- [ ] 错误处理是否完善
- [ ] 用户提示是否友好

#### 代码质量审查
- [ ] 代码是否符合规范
- [ ] 是否有代码重复
- [ ] 变量命名是否清晰
- [ ] 注释是否必要且准确

#### 安全审查
- [ ] 是否有安全漏洞
- [ ] 输入是否验证
- [ ] 敏感信息是否保护
- [ ] 权限检查是否完善

#### 测试审查
- [ ] 测试覆盖率是否达标
- [ ] 测试是否独立
- [ ] Mock是否合理使用
- [ ] 边界条件是否覆盖

#### 性能审查
- [ ] 是否有明显性能问题
- [ ] 是否有内存泄漏
- [ ] 缓存使用是否合理
- [ ] 异步操作是否正确

## ⚠️ 关键注意事项

### 状态管理要求

#### 修改全局状态
```python
# ❌ 不推荐: 直接修改全局状态
_global_variable = new_value

# ✅ 推荐: 通过函数修改并记录
def set_global_state(new_value):
    global _global_variable
    _global_variable = new_value
    logger.info(f"全局状态已更新: {new_value}")
```

#### 测试中的状态重置
```python
# 在测试中必须重置状态
def test_with_global_state():
    # 修改状态
    set_global_state(test_value)
    
    # 测试逻辑
    result = function_with_state()
    
    # 必须重置
    set_global_state(None)
```

### 测试隔离要求

#### 使用fixture管理状态
```python
@pytest.fixture(autouse=True)
def reset_all_states():
    """重置所有全局状态"""
    from agent_tools import set_rag_engine
    from command_recommender import reset_recommender_state
    
    # 重置前
    original_rag = get_rag_engine()
    original_recommender = get_recommender()
    
    yield
    
    # 重置后
    set_rag_engine(original_rag)
    reset_recommender_state(original_recommender)
```

#### 避免测试间状态污染
```python
# ❌ 不推荐: 使用全局变量在测试间共享
test_data = []

def test_1():
    test_data.append("data1")
    
def test_2():
    # test_2可能受到test_1的影响
    assert len(test_data) == 0  # 可能失败

# ✅ 推荐: 每个测试独立
def test_1():
    data = ["data1"]
    assert len(data) == 1

def test_2():
    data = ["data2"]
    assert len(data) == 1
```

### 向后兼容要求

#### 保持接口稳定性
```python
# ✅ 推荐: 保持现有接口，添加新参数
def process_data(data: str, new_param: str = "default") -> str:
    """处理数据，保持向后兼容"""
    if new_param != "default":
        # 新功能
        return advanced_process(data, new_param)
    else:
        # 原有逻辑
        return simple_process(data)

# ❌ 不推荐: 破坏现有接口
def process_data(data: str, new_param: str) -> str:  # 缺少默认值，破坏兼容
    return advanced_process(data, new_param)
```

#### 数据格式兼容
```python
# 使用版本化数据结构
class DataV1:
    def __init__(self, name: str):
        self.name = name
        self.version = "v1"

class DataV2:
    def __init__(self, name: str, age: int = 0):
        self.name = name
        self.age = age
        self.version = "v2"
    
    @classmethod
    def from_v1(cls, v1_data: DataV1) -> 'DataV2':
        """从V1数据升级"""
        return cls(v1_data.name, age=0)  # 提供默认值
```

### 性能影响评估

#### 内存管理
```python
# ❌ 不推荐: 不释放资源
def process_large_file(file_path: str):
    with open(file_path) as f:
        data = f.read()  # 大文件可能占用大量内存
    return process(data)

# ✅ 推荐: 流式处理
def process_large_file(file_path: str):
    with open(file_path) as f:
        for chunk in f:  # 流式读取
            yield process(chunk)
```

#### 缓存策略
```python
# ✅ 推荐: 合理使用缓存
@lru_cache(maxsize=100)
def expensive_computation(data: str) -> str:
    """昂贵的计算，使用缓存"""
    return complex_algorithm(data)

# 缓存失效策略
def update_data(data_id: str):
    """更新数据时使相关缓存失效"""
    expensive_computation.cache_clear()  # 清除缓存
    # 或 selectively invalidate
    if data_id in expensive_computation.cache:
        del expensive_computation.cache[data_id]
```

## 📝 修改前检查清单

### 开始修改前
- [ ] 理解现有代码逻辑
- [ ] 确认修改影响范围
- [ ] 检查是否有相关测试
- [ ] 评估向后兼容性
- [ ] 设计错误处理方案
- [ ] 准备回退计划

### 修改过程中
- [ ] 先读取文件再修改
- [ ] 最小化修改范围
- [ ] 保持代码风格一致
- [ ] 添加适当的日志
- [ ] 同步更新测试
- [ ] 同步更新文档
- [ ] **如引入新依赖**：遵循依赖管理规范（见CODE_STANDARDS.md）
  - [ ] 确保兼容Python 3.13.13最新稳定版本
  - [ ] 更新requirements.txt
  - [ ] 更新install_deps.sh脚本
  - [ ] 更新verify_deps.sh脚本
  - [ ] 更新check_prereqs.sh脚本
  - [ ] 运行依赖验证脚本

### 修改完成后
- [ ] 运行相关测试
- [ ] 检查测试覆盖率
- [ ] 手动测试修改功能
- [ ] 确认没有副作用
- [ ] 更新相关文档
- [ ] 记录重要变更
- [ ] **必须添加单元测试**（强制要求）
  - [ ] 为新代码编写单元测试
  - [ ] 为修改的代码更新单元测试
  - [ ] 确保测试覆盖率≥95%
  - [ ] 测试正常情况和异常情况
  - [ ] 测试边界条件
- [ ] **必须完善相关文档**（强制要求）
  - [ ] 更新或创建README.md相关章节
  - [ ] 更新或创建TUTORIAL.md相关教程
  - [ ] 更新技术文档（如适用）
  - [ ] 添加使用示例
  - [ ] 更新API文档（如适用）

## 🧪 测试验证流程

### 测试类型

#### 单元测试
- 测试单个函数或方法
- 使用Mock隔离依赖
- 覆盖正常和异常情况
- 快速执行

#### 集成测试
- 测试模块间交互
- 测试数据流
- 测试状态管理
- 较慢执行

#### 端到端测试
- 测试完整工作流
- 测试用户场景
- 测试错误恢复
- 最慢执行

### 测试命令
```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/test_rag_engine.py -v

# 运行测试并检查覆盖率
python -m pytest tests/test_rag_engine.py --cov=rag_engine --cov-report=term-missing

# 并行运行测试
python -m pytest tests/ -n auto

# 只运行失败的测试
python -m pytest tests/ --lf
```

## 📚 参考文档位置

### 项目文档
- 项目架构: `AI_KNOWLEDGE_BASE/ARCHITECTURE.md`
- 模块详解: `AI_KNOWLEDGE_BASE/MODULE_GUIDES.md`
- 代码规范: `AI_KNOWLEDGE_BASE/CODE_STANDARDS.md`
- 测试指南: `AI_KNOWLEDGE_BASE/TESTING_GUIDELINES.md`

### 项目配置
- 系统提示: `.devin/SYSTEM_PROMPT.md`
- Agent配置: `.devin/AGENTS.md`
- 项目配置: `src/config.py`

### 技术文档
- README.md: 项目概述
- TUTORIAL.md: 使用教程
- docs/: 详细技术文档

遵循这些标准流程可以确保代码质量和项目稳定性。