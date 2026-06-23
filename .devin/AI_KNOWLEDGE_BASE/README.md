# AI知识库 (AI Knowledge Base)

本目录包含项目专用的AI提示词文件，用于帮助AI助手更好地理解和处理复杂项目。

## 📚 文件说明

### 核心提示词（所有任务必须读取）

#### PROJECT_OVERVIEW.md
- **用途**: 项目整体概览
- **内容**: 项目定位、架构概览、核心模块职责、设计原则
- **适用场景**: 所有任务开始前必读

#### ARCHITECTURE.md  
- **用途**: 系统架构设计
- **内容**: 架构层次、设计模式、模块依赖、接口设计、安全架构
- **适用场景**: 代码修改、新功能开发

#### CODE_STANDARDS.md
- **用途**: 代码规范
- **内容**: Python风格、文档字符串、错误处理、日志记录、异步编程
- **适用场景**: 所有代码编写任务

#### WORKFLOWS.md
- **用途**: 开发流程标准
- **内容**: 代码修改流程、新功能开发流程、Bug修复流程、测试验证
- **适用场景**: 所有开发任务

### 模块详细提示词（根据任务类型选择性读取）

#### MODULE_GUIDES.md
- **用途**: 核心模块详细说明
- **内容**: RAG引擎、Agent系统、命令推荐、网络搜索、OCR处理等模块详解
- **适用场景**: 修改特定模块时

#### TESTING_GUIDELINES.md
- **用途**: 测试编写指南
- **内容**: 测试类型、fixture使用、Mock规范、覆盖率要求
- **适用场景**: 编写或修改测试

#### TRAP_AVOIDANCE.md
- **用途**: 常见问题规避
- **内容**: 状态管理陷阱、测试隔离陷阱、性能陷阱、安全陷阱
- **适用场景**: 所有开发任务（避免引入新问题）

### 工具使用提示词（使用工具时读取）

#### TOOL_USAGE.md
- **用途**: 工具使用指南
- **内容**: 可用工具清单、安全检查、工具组合模式、限制说明
- **适用场景**: 使用工具链时

## 🎯 使用指南

### 任务类型与提示词对应

#### 代码修改任务
```
必读:
- PROJECT_OVERVIEW.md
- ARCHITECTURE.md
- CODE_STANDARDS.md
- WORKFLOWS.md
- MODULE_GUIDES.md（相关模块）
- TRAP_AVOIDANCE.md

选读:
- TOOL_USAGE.md（如果使用工具）
```

#### 测试任务
```
必读:
- PROJECT_OVERVIEW.md
- TESTING_GUIDELINES.md
- MODULE_GUIDES.md（相关模块）

选读:
- CODE_STANDARDS.md（代码风格）
- TRAP_AVOIDANCE.md（测试隔离）
```

#### 新功能开发
```
必读:
- PROJECT_OVERVIEW.md
- ARCHITECTURE.md
- CODE_STANDARDS.md
- WORKFLOWS.md
- MODULE_GUIDES.md（所有相关模块）
- TRAP_AVOIDANCE.md
- TESTING_GUIDELINES.md
```

#### Bug修复
```
必读:
- PROJECT_OVERVIEW.md
- CODE_STANDARDS.md
- WORKFLOWS.md
- MODULE_GUIDES.md（相关模块）
- TRAP_AVOIDANCE.md

选读:
- TESTING_GUIDELINES.md（如果需要添加测试）
```

## 📋 AI执行流程（强制）

当AI执行任何任务时，必须按照以下顺序操作：

1. **读取全局配置**
   - `~/.config/devin/AI_DEBUGGING_WORKFLOW.md`
   - `~/.config/devin/AGENTS.md`

2. **读取项目配置**
   - `.devin/AGENTS.md`

3. **读取系统提示**
   - `.devin/SYSTEM_PROMPT.md`

4. **读取项目知识库提示词**（根据任务类型）
   - 核心提示词（PROJECT_OVERVIEW + ARCHITECTURE + CODE_STANDARDS + WORKFLOWS）
   - 相关模块提示词
   - 陷阱规避提示词

5. **创建任务追踪**
   - 使用 `todo_write` 工具

6. **执行任务**
   - 遵循标准流程
   - 更新任务状态

## 🚨 重要提醒

### 为什么需要这些提示词？

项目复杂度高：
- 68个Python文件，56个测试文件
- 10+个核心功能模块
- 复杂的状态管理和依赖关系
- 严格的测试隔离要求

### 这些提示词的作用

1. **理解项目**: 快速理解项目架构和设计意图
2. **遵循规范**: 确保代码风格一致性和质量
3. **避免陷阱**: 避免常见的状态管理、测试隔离等问题
4. **标准流程**: 遵循标准开发和测试流程
5. **工具使用**: 正确使用工具链

### 不遵循的后果

- 可能引入新的Bug
- 破坏现有功能
- 测试失败
- 代码质量下降
- 维护成本增加

## 🔄 维护和更新

### 何时更新提示词
- 添加新模块时，更新MODULE_GUIDES.md
- 修改架构时，更新ARCHITECTURE.md
- 更新代码规范时，更新CODE_STANDARDS.md
- 发现新陷阱时，更新TRAP_AVOIDANCE.md
- 添加新工具时，更新TOOL_USAGE.md

### 版本控制
- 所有提示词文件应该纳入版本控制
- 重要修改应该记录变更历史
- 定期审核提示词的有效性

## 📊 使用统计

### 提示词覆盖情况
- ✅ PROJECT_OVERVIEW.md - 项目概览
- ✅ ARCHITECTURE.md - 系统架构
- ✅ CODE_STANDARDS.md - 代码规范
- ✅ WORKFLOWS.md - 开发流程
- ✅ MODULE_GUIDES.md - 模块详解
- ✅ TESTING_GUIDELINES.md - 测试指南
- ✅ TRAP_AVOIDANCE.md - 陷阱规避
- ✅ TOOL_USAGE.md - 工具使用

### 文件大小
- PROJECT_OVERVIEW.md: ~7KB
- ARCHITECTURE.md: ~8KB
- CODE_STANDARDS.md: ~11KB
- WORKFLOWS.md: ~10KB
- MODULE_GUIDES.md: ~12KB
- TESTING_GUIDELINES.md: ~10KB
- TRAP_AVOIDANCE.md: ~15KB
- TOOL_USAGE.md: ~11KB

**总计**: ~84KB的提示词内容

## 🎯 预期效果

### 对AI能力的提升
1. **理解力**: 深入理解项目架构和设计意图
2. **准确性**: 避免常见错误和陷阱
3. **效率**: 标准化流程，减少重复工作
4. **质量**: 遵循最佳实践，保证代码质量

### 对项目质量的提升
1. **稳定性**: 减少引入新问题
2. **可维护性**: 代码风格一致，易于维护
3. **可靠性**: 充分测试，功能可靠
4. **安全性**: 遵循安全规范

---

**创建日期**: 2026-06-12  
**维护者**: AI Development Team  
**用途**: AI辅助开发提示词库