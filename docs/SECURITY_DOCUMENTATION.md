# 内容安全扫描器文档

## 概述

内容安全扫描器 (`content_security.py`) 是一个专门用于防止基于文档的提示词攻击的安全系统。它自动扫描用户添加到知识库的文档，检测并阻止潜在的安全威胁。

## 核心功能

### 1. 提示词注入检测

检测文档中试图改变AI行为的指令，例如：
- "Ignore all previous instructions"
- "Disregard the above instructions"
- "Override previous instructions"
- "Forget previous instructions"

### 2. 角色劫持防护

防止恶意文档试图改变AI的角色或身份，例如：
- "You are now a hacker"
- "Act as a criminal"
- "Pretend to be a thief"
- "Your new role is..."

### 3. 高风险关键词识别

识别与危险操作相关的词汇，例如：
- kill, destroy, erase, delete, remove
- override, bypass, ignore, disregard
- inject, infection, malware, virus
- hack, attack, breach, compromise, steal

### 4. 可疑模式检测

检测可能用于隐藏恶意指令的模式，例如：
- 过度的字符重复（20个以上相同字符）
- Base64编码的内容
- 其他混淆技术

### 5. 威胁等级评估

系统使用5级威胁分类：
- **SAFE**: 未检测到安全问题
- **LOW**: 检测到轻微风险（如高风险关键词）
- **MEDIUM**: 检测到中等威胁（如角色定义）
- **HIGH**: 检测到严重威胁（如提示词注入）
- **CRITICAL**: 极端威胁（预留）

## 系统集成

### RAG引擎集成

在 `rag_engine.py` 中，添加文档时会自动进行安全检查：

```python
# 启用安全扫描
engine = RAGEngine(enable_security=True)  # 默认启用

# 禁用安全扫描
engine = RAGEngine(enable_security=False)
```

### Skill生成集成

在 `knowledge_to_skills.py` 中，生成skill时会进行内容过滤：

```python
# 启用安全扫描
engine = KnowledgeToSkillsEngine(
    index_dir="./index_storage",
    enable_security=True  # 默认启用
)

# 禁用安全扫描
engine = KnowledgeToSkillsEngine(
    index_dir="./index_storage",
    enable_security=False
)
```

## 使用示例

### 基本使用

```python
from content_security import ContentSecurityScanner, SkillSecurityFilter

# 创建扫描器
scanner = ContentSecurityScanner()

# 扫描内容
content = "这是一个关于Cloudflare配置的技术文档"
is_safe, issues = scanner.scan_content(content, filename="document.md")

if is_safe:
    print("内容安全")
else:
    print(f"检测到 {len(issues)} 个安全问题")
    for issue in issues:
        print(f"- {issue.issue_type}: {issue.description}")

# 评估整体威胁等级
threat_level = scanner.assess_overall_threat(issues)
print(f"威胁等级: {threat_level.value}")
```

### Skill过滤

```python
from content_security import SkillSecurityFilter

# 创建过滤器
filter = SkillSecurityFilter()

# 过滤skill内容
safe_content, is_allowed, issues = filter.filter_skill_content(
    content, 
    filename="skill.md"
)

if is_allowed:
    print(f"内容已净化: {safe_content[:100]}...")
else:
    print("内容包含严重安全问题，已拒绝生成")
```

### 判断是否应该生成Skill

```python
# 检查是否应该生成skill
should_generate, message = filter.should_generate_skill(content, filename="doc.md")

if should_generate:
    print(f"允许生成skill: {message}")
else:
    print(f"拒绝生成skill: {message}")
```

## 安全策略

### 严重威胁（HIGH）

当检测到严重威胁时：
- **文档添加**: 拒绝添加该文档到知识库
- **Skill生成**: 拒绝生成skill
- **日志**: 记录详细的安全警告

### 中等威胁（MEDIUM）

当检测到中等威胁时：
- **文档添加**: 允许添加但发出警告
- **Skill生成**: 净化内容后允许生成
- **日志**: 记录警告信息

### 轻微威胁（LOW）

当检测到轻微威胁时：
- **文档添加**: 正常添加，记录信息日志
- **Skill生成**: 正常生成，记录信息日志
- **日志**: 记录信息级别的通知

## 测试

### 运行安全扫描器测试

```bash
# 测试安全扫描器
python -m pytest test_content_security.py -v

# 查看测试覆盖率
python -m pytest test_content_security.py -v --cov=content_security --cov-report=term-missing
```

### 测试覆盖

当前测试覆盖率：85%

测试用例包括：
- 提示词注入检测测试
- 角色劫持检测测试
- 高风险关键词识别测试
- 可疑模式检测测试
- 内容净化功能测试
- 威胁等级评估测试
- 真实世界安全文档测试
- 性能测试（大文档扫描）

## 最佳实践

1. **始终启用安全扫描**: 在生产环境中建议始终保持安全扫描启用
2. **定期审查日志**: 定期检查安全日志，了解潜在的安全事件
3. **更新模式库**: 根据新的攻击模式定期更新安全扫描模式
4. **用户教育**: 教育用户不要添加包含恶意指令的文档
5. **测试安全功能**: 在部署前充分测试安全功能

## 限制和注意事项

1. **误报可能**: 某些正常的技术文档可能包含类似模式，系统会进行智能判断
2. **性能影响**: 安全扫描会增加少量处理时间，但影响最小（<100ms）
3. **非绝对防护**: 安全扫描是防御层之一，不能替代其他安全措施
4. **模式依赖**: 安全检测依赖于预定义的模式，无法检测未知的新攻击

## 配置选项

### 启用/禁用安全扫描

```python
# 在RAG引擎中
engine = RAGEngine(enable_security=True/False)

# 在Skill生成引擎中
engine = KnowledgeToSkillsEngine(
    index_dir="./index_storage",
    enable_security=True/False
)
```

### 日志配置

```python
# 启用详细日志
scanner = ContentSecurityScanner(enable_logging=True)

# 禁用日志
scanner = ContentSecurityScanner(enable_logging=False)
```

## 故障排除

### 问题：文档被拒绝添加

**可能原因**: 文档包含提示词注入模式
**解决方案**: 
1. 检查文档内容是否包含 "ignore instructions" 等模式
2. 修改文档，移除可能被误判的内容
3. 如确认为误报，考虑禁用安全扫描（不推荐）

### 问题：Skill生成失败

**可能原因**: 内容包含严重安全问题
**解决方案**:
1. 检查安全日志，了解具体问题
2. 净化或修改源文档
3. 使用 `SkillSecurityFilter` 手动净化内容

## 未来改进

1. **机器学习增强**: 使用ML模型提高检测准确性
2. **自适应阈值**: 根据历史数据调整检测敏感度
3. **用户反馈**: 允许用户标记误报，持续改进
4. **实时更新**: 从远程服务器更新威胁模式库
5. **更详细的报告**: 提供更详细的安全分析报告
