# 项目特定AI助手配置

本文件定义了本项目特定的AI助手工作标准和补充要求。

## 🎯 配置层级

**优先级顺序**:
1. **全局配置**: `~/.config/devin/AI_DEBUGGING_WORKFLOW.md` (必须首先遵循)
2. **全局标准**: `~/.config/devin/AGENTS.md` (通用质量标准)
3. **项目补充**: 本文件 (项目特定要求和补充)
4. **系统提示**: `.devin/SYSTEM_PROMPT.md` (AI执行时必须首先读取)

## 📋 项目特定要求

### 技术栈
- **主要语言**: Python 3.13
- **测试框架**: pytest
- **代码规范**: PEP 8
- **依赖管理**: pip/venv
- **主要库**: 
  - ChromaDB (向量数据库)
  - LlamaIndex (RAG框架)
  - Ollama (LLM接口)

### AI执行强制要求（最高优先级）
- **必须先读取系统提示**: AI在执行任何任务前必须使用 `read_system_prompt` 工具读取 `.devin/SYSTEM_PROMPT.md`
- **必须读取配置文件**: 按优先级读取全局和项目配置文件
- **必须读取项目知识库提示词**（MUST READ - 新增强制步骤）：
  - **必须**在开始任何代码修改或复杂任务前，读取 `.devin/AI_KNOWLEDGE_BASE/` 中的提示词文件
  - **核心提示词**（所有任务都必须读取）：
    - `PROJECT_OVERVIEW.md` - 项目概览，理解项目整体架构
    - `ARCHITECTURE.md` - 系统架构设计，理解模块交互
    - `CODE_STANDARDS.md` - 代码规范，确保代码风格一致
    - `WORKFLOWS.md` - 开发流程，遵循标准流程
  - **根据任务类型选择性读取**：
    - 代码修改任务：核心提示词 + `MODULE_GUIDES.md` + `TRAP_AVOIDANCE.md`
    - 测试任务：`PROJECT_OVERVIEW.md` + `TESTING_GUIDELINES.md` + `MODULE_GUIDES.md`
    - 工具使用任务：`TOOL_USAGE.md` + 相关模块详解
- **必须使用任务追踪**: 使用 `todo_write` 工具创建和更新任务列表
- **必须遵循质量标准**: 测试覆盖率≥95%，所有测试必须通过

### 项目特定命令
```bash
# 激活虚拟环境
source venv/bin/activate

# 运行测试
python -m pytest tests/ -v

# 覆盖率检查
python -m pytest tests/ --cov=<module_name> --cov-report=term-missing

# 特定模块测试
python -m pytest tests/test_knowledge_snapshot.py
```

### 项目特定质量标准
- ✅ 测试覆盖率 ≥ 95% (严格要求)
- ✅ 所有测试必须通过
- ✅ 遵循项目现有的代码结构
- ✅ 添加适当的错误处理（特别是JSON解析、文件操作）
- ✅ 保持与ChromaDB和LlamaIndex的兼容性

### 新增强制要求（MUST - 必须遵守）

#### 1. 依赖管理要求（强制）
- ✅ 引入新依赖时必须使用兼容Python 3.13.13的最新稳定版本
- ✅ 必须更新requirements.txt
- ✅ 必须更新install_deps.sh脚本
- ✅ 必须更新verify_deps.sh脚本
- ✅ 必须更新check_prereqs.sh脚本
- ✅ 必须运行验证脚本确认

**违反依赖管理要求的代码将被拒绝交付。**

#### 2. 测试要求（强制）
- ✅ 修改代码后必须添加单元测试
- ✅ 新功能必须编写完整测试
- ✅ Bug修复必须编写复现测试
- ✅ 确保测试覆盖率≥95%
- ✅ 测试必须覆盖边界条件

**无测试的代码修改将被拒绝交付。**

#### 3. 文档要求（强制）
- ✅ 完成项目需求后必须完善文档
- ✅ 必须更新README.md相关章节
- ✅ 必须更新或创建TUTORIAL.md相关教程
- ✅ 必须添加使用示例
- ✅ 必须更新技术文档（如适用）

**缺少文档的功能将被拒绝交付。**

## 🔧 项目特定工作流程补充

### 知识库相关任务
处理知识库快照、RAG引擎等相关任务时：
- 额外检查ChromaDB连接状态
- 验证向量数据库完整性
- 确保文档索引正确性
- 测试OCR处理功能（如果涉及）

### Agent相关任务
处理多Agent协作任务时：
- 测试消息总线通信
- 验证任务调度逻辑
- 检查Agent注册表
- 确保结果集成正确

### 文档处理任务
处理文档加载和OCR任务时：
- 测试多种文件格式支持
- 验证OCR准确性
- 检查缓存机制
- 确保内存管理有效

### 命令推荐系统相关任务
处理智能命令推荐系统时：
- 验证推荐算法正确性
- 测试上下文管理功能
- 检查学习引擎更新
- 确保用户偏好存储正常
- 验证CLI集成（推荐系统仅在CLI中实现，桌面应用/托盘进程不集成）
- 测试推荐性能和响应时间

## 🚨 项目特定禁止行为

### 本项目特别禁止
- ❌ 直接修改ChromaDB数据文件
- ❌ 破坏知识库索引结构
- ❌ 修改Agent注册表格式
- ❌ 更改OCR处理器接口
- ❌ 破坏快照数据完整性
- ❌ 修改推荐引擎核心算法
- ❌ 破坏用户偏好存储结构
- ❌ 泄露用户命令历史数据
- ❌ 修改推荐系统权重计算逻辑

### 数据安全
- ⚠️ 处理用户文档时注意隐私保护
- ⚠️ 快照数据包含敏感路径，需谨慎处理
- ⚠️ OCR结果可能包含敏感信息，需适当过滤
- ⚠️ 推荐系统记录用户命令历史，需保护用户行为数据
- ⚠️ 用户偏好存储可能包含使用习惯，需加密保存
- ⚠️ 推荐系统上下文信息可能包含敏感操作，需最小化存储

## 📊 项目结构理解

### 核心模块
- `knowledge_snapshot.py` - 知识库快照管理
- `rag_engine.py` - RAG搜索引擎
- `react_engine.py` - ReAct推理引擎
- `agent_*.py` - Agent相关模块
- `ocr_processor/` - OCR处理模块
- `query_interface.py` - 统一查询接口
- `command_recommender/` - 智能命令推荐系统

### 测试结构
- `tests/test_knowledge_snapshot.py` - 快照测试
- `tests/test_rag_engine.py` - RAG测试
- `tests/test_agent_*.py` - Agent测试
- `tests/test_ocr_*.py` - OCR测试
- `tests/test_command_recommender/` - 推荐系统测试

## 🎯 项目特定交付标准

### 必须包含
1. 问题已解决，用户可验证
2. 代码修改最小化且健壮
3. 全面的单元测试保护
4. 95%+测试覆盖率
5. 详细的工作流程记录
6. **项目特定**: 知识库完整性验证

### 项目验证步骤
- [ ] 运行相关模块测试
- [ ] 检查ChromaDB连接
- [ ] 验证知识库索引
- [ ] 测试Agent协作（如涉及）
- [ ] 验证OCR功能（如涉及）
- [ ] 测试命令推荐系统功能
- [ ] 验证推荐算法准确性
- [ ] 检查用户偏好存储
- [ ] 测试推荐系统CLI集成（推荐系统仅在CLI中实现，桌面应用/托盘进程不集成）
- [ ] 测试桌面应用（托盘进程）自身功能（如涉及）

## 📚 项目参考文档

### 项目文档
- **README.md**: 项目整体说明
- **TUTORIAL.md**: 使用教程
- **CHANGELOG.md**: 变更日志

### 技术文档
- **docs/**: 详细技术文档
- **examples/**: 示例代码

### 全局配置
- **全局工作流程**: `~/.config/devin/AI_DEBUGGING_WORKFLOW.md`
- **全局标准**: `~/.config/devin/AGENTS.md`

### AI知识库（新增 - 强制阅读）
- **项目知识库**: `.devin/AI_KNOWLEDGE_BASE/`
  - `PROJECT_OVERVIEW.md` - 项目概览
  - `ARCHITECTURE.md` - 系统架构
  - `CODE_STANDARDS.md` - 代码规范
  - `WORKFLOWS.md` - 开发流程
  - `MODULE_GUIDES.md` - 模块详解
  - `TESTING_GUIDELINES.md` - 测试指南
  - `TRAP_AVOIDANCE.md` - 陷阱规避
  - `TOOL_USAGE.md` - 工具使用
- **重要**: 所有代码修改任务前必须先读取这些文件

## 🔍 项目常见问题

### ChromaDB相关问题
- **连接超时**: 检查ChromaDB服务状态
- **索引损坏**: 使用快照恢复功能
- **内存不足**: 调整批量处理大小

### OCR相关问题
- **识别率低**: 检查图像质量
- **处理缓慢**: 启用缓存机制
- **内存泄漏**: 清理临时文件

### Agent相关问题
- **协作失败**: 检查消息总线
- **任务卡死**: 验证任务调度器
- **结果丢失**: 检查结果集成器

### 推荐系统相关问题
- **推荐不准确**: 检查上下文管理和权重设置
- **学习功能异常**: 验证用户偏好存储
- **性能问题**: 调整推荐算法复杂度
- **集成失败**: 检查CLI集成（推荐系统仅在CLI中实现，桌面应用/托盘进程不集成）

---

**项目配置版本**: 1.0
**最后更新**: 2026-06-12
**适用项目**: ollama-qwen-coder-rag-lib-agent
**全局配置**: `~/.config/devin/AI_DEBUGGING_WORKFLOW.md`
