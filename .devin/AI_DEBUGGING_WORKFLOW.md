# AI 调试工作流程指南

本文档描述了在项目中遇到错误时的标准调试和解决流程，供AI助手参考。

## 🎯 工作流程概览

当用户报告错误时，按照以下步骤进行系统性调试：

### 1. 错误分析阶段

#### 1.1 理解错误信息
- 仔细分析用户提供的错误信息
- 识别错误类型（JSON解析错误、导入错误、运行时错误等）
- 定位错误发生的具体位置（文件名、行号、函数名）

#### 1.2 探索项目结构
```bash
# 查看项目文件结构
find_file_by_name(pattern="**/*.py")

# 查看当前目录
exec(command="ls -la")

# 搜索相关代码
grep(pattern="错误相关的关键词")
```

#### 1.3 定位问题代码
- 找到报错的具体函数/方法
- 阅读相关代码实现
- 理解代码的业务逻辑

### 2. 问题诊断阶段

#### 2.1 确定根本原因
- 分析代码逻辑，找出导致错误的根本原因
- 常见问题类型：
  - 缺少错误处理
  - 数据格式不匹配
  - 边界条件未考虑
  - 依赖项问题

#### 2.2 验证问题假设
- 创建最小复现用例
- 检查相关数据文件
- 验证环境配置

### 3. 解决方案设计阶段

#### 3.1 设计修复方案
- 制定具体的修复策略
- 考虑方案的副作用
- 确保不会引入新的问题

#### 3.2 实施代码修复
```python
# 示例：添加错误处理
def list_snapshots(self) -> List[Dict]:
    """列出所有快照"""
    snapshots = []
    
    for snapshot_file in sorted(self.snapshot_dir.glob("*.json"), reverse=True):
        try:
            with open(snapshot_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            snapshots.append({
                "snapshot_id": data['snapshot_id'],
                "timestamp": data['timestamp'],
                "document_count": len(data['documents']),
                "total_chunks": data['total_chunks'],
                "trigger": data['metadata'].get('trigger', 'unknown'),
                "file": str(snapshot_file)
            })
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"跳过损坏的快照文件 {snapshot_file.name}: {e}")
            continue
    
    return snapshots
```

#### 3.3 清理损坏数据
```bash
# 删除损坏的文件
exec(command="rm 损坏的文件路径")
```

### 4. 测试验证阶段

#### 4.1 添加单元测试
- 为修复的代码添加全面的单元测试
- 覆盖正常情况和各种异常情况
- 确保测试覆盖率达到95%以上

**测试用例设计原则：**
- 正常情况测试
- 边界条件测试
- 异常处理测试
- 错误恢复测试

#### 4.2 运行测试并检查覆盖率
```bash
# 运行测试
exec(command="source venv/bin/activate && python -m pytest tests/test_knowledge_snapshot.py -v")

# 检查覆盖率
exec(command="source venv/bin/activate && python -m pytest tests/test_knowledge_snapshot.py --cov=knowledge_snapshot --cov-report=term-missing")
```

#### 4.3 验证修复效果
- 确保所有测试通过
- 验证覆盖率达标
- 手动验证用户报告的问题已解决

### 5. 文档和总结阶段

#### 5.1 创建工作追踪
使用 `todo_write` 工具追踪任务进度：
```python
todo_write([
    {"content": "分析错误信息", "status": "completed"},
    {"content": "定位问题代码", "status": "completed"},
    {"content": "实施代码修复", "status": "in_progress"},
    {"content": "添加单元测试", "status": "pending"},
    {"content": "验证修复效果", "status": "pending"}
])
```

#### 5.2 生成解决方案总结
- 描述问题原因
- 说明修复方案
- 列出测试覆盖情况
- 提供后续建议

## 📋 实际案例：JSON解析错误修复

### 问题报告
```
❯ /snapshot-list
❌ 获取快照列表失败: Expecting value: line 15 column 19 (char 544)
```

### 解决步骤

1. **错误分析**
   - 错误类型：JSON解析错误
   - 错误位置：`list_snapshots` 方法
   - 可能原因：JSON文件损坏或格式不正确

2. **代码探索**
   - 找到 `knowledge_snapshot.py` 中的 `list_snapshots` 方法
   - 发现缺少错误处理，任何JSON解析错误都会导致整个操作失败

3. **问题诊断**
   - 检查快照目录，发现多个544字节的JSON文件不完整
   - 这些文件在 `"total_chunks":` 后面缺少值和metadata字段

4. **解决方案**
   - 在 `list_snapshots` 方法中添加try-catch错误处理
   - 跳过损坏的JSON文件，记录警告日志
   - 删除5个损坏的快照文件

5. **测试验证**
   - 添加针对 `list_snapshots` 的单元测试：
     - `test_list_snapshots_with_corrupted_json` - 处理损坏JSON
     - `test_list_snapshots_with_missing_metadata` - 处理缺少字段
     - `test_list_snapshots_with_missing_required_field` - 处理缺少必需字段
     - `test_list_snapshots_empty_directory` - 处理空目录
   - 测试覆盖率达到99%（超过95%目标）

6. **结果验证**
   - 46个测试全部通过
   - `/snapshot-list` 命令正常工作
   - 系统对损坏文件具有容错能力

## 🛠️ 常用工具和命令

### 文件操作
```bash
# 查找文件
find_file_by_name(pattern="**/*.py")

# 读取文件
read(file_path="/path/to/file")

# 编辑文件
edit(file_path="/path/to/file", old_string="原内容", new_string="新内容")

# 写入文件
write(file_path="/path/to/file", content="内容")
```

### 代码搜索
```bash
# 搜索代码
grep(pattern="关键词", output_mode="content")

# 搜索文件
grep(pattern="关键词", output_mode="files_with_matches")
```

### 测试和覆盖率
```bash
# 运行测试
python -m pytest tests/test_file.py -v

# 运行测试并检查覆盖率
python -m pytest tests/test_file.py --cov=module_name --cov-report=term-missing
```

### 环境操作
```bash
# 使用虚拟环境
source venv/bin/activate && python command

# 查看目录
ls -la

# 删除文件
rm file_path
```

## 📝 最佳实践

### 代码修复原则
1. **最小化修改**：只修改必要的代码，避免过度重构
2. **向后兼容**：确保修改不会破坏现有功能
3. **错误处理**：添加适当的错误处理和日志记录
4. **代码风格**：遵循项目现有的代码风格

### 测试编写原则
1. **全面覆盖**：覆盖正常、边界、异常情况
2. **独立性**：每个测试应该独立运行
3. **可读性**：测试名称和注释应该清晰
4. **覆盖率**：目标覆盖率95%以上

### 沟通原则
1. **及时反馈**：每完成一个步骤及时更新进度
2. **清晰解释**：清楚说明问题原因和解决方案
3. **数据说话**：用测试结果和覆盖率数据支撑结论
4. **用户确认**：重要修改前等待用户确认

## 🎯 质量标准

### 代码质量标准
- 所有测试必须通过
- 代码覆盖率 ≥ 95%
- 遵循PEP 8代码规范
- 添加适当的错误处理和日志

### 文档标准
- 修复过程有详细记录
- 测试用例有清晰注释
- 修复后有总结报告

### 交付标准
- 用户报告的问题已解决
- 系统更加健壮（容错能力提升）
- 有相应的测试保护
- 有文档记录修复过程

---

**最后更新**: 2026-06-12
**适用项目**: ollama-qwen-coder-rag-lib-agent
**维护者**: AI Development Team
