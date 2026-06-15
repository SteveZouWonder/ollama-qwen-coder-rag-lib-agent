# 实战场景示例

> 本文档提供了12个实战场景示例，展示如何在不同场景中使用智能文档+代码助手，包括v4.1.0新增的文件管理和会话管理功能。

---

## 场景1：学术研究 - 论文综述

**目标**: 快速理解多篇论文的核心内容，生成文献综述

```bash
# 准备论文文档
mkdir papers
cp 论文1.pdf papers/
cp 论文2.pdf papers/
cp 论文3.pdf papers/

# 启动助手
python query_interface.py --data ./papers

# 查询示例
>>> /ask 总结这三篇论文的核心贡献是什么？
>>> /ask 对比它们的研究方法论有何不同？
>>> /ask 这些论文的主要创新点有哪些？
>>> /ask 根据这些论文，该领域的研究趋势是什么？
```

**预期效果**:
- 快速提取每篇论文的核心观点
- 对比不同论文的方法和结论
- 识别研究趋势和热点
- 生成结构化的文献综述

**v4.1.0优化**: 使用文件管理功能追踪论文文件
```bash
# 查看知识库中的论文文件
>>> /file-list
📁 共有 3 个文件:
  📄 论文1.pdf
  📊 大小: 5.20 MB
  🏷️ 类型: permanent

# 查看论文文件详情
>>> /file-info 论文1.pdf
📄 文件信息: 论文1.pdf
🔢 访问次数: 15
📄 文档数: 120
🧩 Chunk数: 450
```

---

## 场景2：代码开发 - 新功能实现

**目标**: 根据需求描述生成完整的功能代码

```bash
# 启动Agent模式
python query_interface.py

# 创建工作会话
>>> /session-new 用户注册功能开发

# 任务示例
>>> /agent 为用户管理系统添加用户注册功能
>>> /agent 使用Flask框架，需要包含表单验证
>>> /agent 生成单元测试，确保功能正常
>>> /agent 添加API文档注释
```

**Agent执行流程**:
1. 分析现有代码结构
2. 生成用户注册代码
3. 添加表单验证
4. 创建单元测试
5. 运行测试验证
6. 添加文档注释

**v4.1.0优化**: 使用会话管理功能组织开发任务
```bash
# 为不同功能创建独立会话
>>> /session-new 用户注册功能
>>> /session-new 登录功能开发
>>> /session-new 权限管理

# 切换会话继续工作
>>> /session-switch abc123
✅ 已切换到会话: 用户注册功能
💬 该会话有 15 条消息
```

---

## 场景3：项目重构 - 代码优化

**目标**: 优化现有代码的性能和可读性

```bash
# 启动Agent模式
python query_interface.py

# 任务示例
>>> /agent 分析utils.py中的性能瓶颈
>>> /agent 优化数据处理函数，提高运行速度
>>> /agent 改进代码可读性，添加注释
>>> /agent 运行性能测试，对比优化前后结果
```

---

## 场景4：文档生成 - API文档

**目标**: 基于代码生成API文档

```bash
# 启动助手
python query_interface.py --data ./src

# 任务示例
>>> /agent 分析所有Python文件，提取API接口
>>> /agent 生成Markdown格式的API文档
>>> /agent 添加使用示例和参数说明
>>> /agent 检查文档与代码的一致性
```

---

## 场景5：数据分析 - 日志分析

**目标**: 分析服务器日志，识别问题和趋势

```bash
# 准备日志文件
mkdir logs
cp server.log logs/

# 启动助手
python query_interface.py --data ./logs

# 查询示例
>>> /ask 日志中主要有哪些错误类型？
>>> /ask 错误发生的时间分布是怎样的？
>>> /ask 哪些API端点出现错误最多？
>>> /ask 生成错误分析报告
```

---

## 场景6：故障排查 - Bug定位

**目标**: 定位和修复代码中的bug

```bash
# 启动Agent模式
python query_interface.py

# 任务示例
>>> /agent 分析错误日志，定位bug位置
>>> /agent 读取相关代码文件
>>> /agent 识别问题的根本原因
>>> /agent 提供修复方案
>>> /agent 验证修复是否有效
```

---

## 场景7：配置迁移 - 系统升级

**目标**: 在系统升级时迁移和验证配置

```bash
# 准备新旧配置文件
mkdir configs
cp old_config.json configs/
cp new_config_template.json configs/

# 启动助手
python query_interface.py --data ./configs

# 查询示例
>>> /ask 对比新旧配置文件的差异
>>> /ask 哪些配置项需要迁移？
>>> /ask 验证新配置的正确性
>>> /ask 生成配置迁移指南
```

---

## 场景8：学习教程 - 技能提升

**目标**: 学习新的技术概念和最佳实践

```bash
# 准备学习资料
mkdir learning
cp 技术文档.md learning/
cp 代码示例.py learning/

# 启动助手
python query_interface.py --data ./learning

# 查询示例
>>> /ask 解释这个技术概念的核心原理
>>> /ask 这个代码示例使用了哪些设计模式？
>>> /ask 如何在实际项目中应用这些技术？
>>> /ask 生成学习路径和练习建议
```

---

## 场景9：团队协作 - 代码审查

**目标**: 进行代码审查，提供改进建议

```bash
# 启动Agent模式
python query_interface.py

# 任务示例
>>> /agent 审查src/目录下的所有Python代码
>>> /agent 检查代码质量和潜在问题
>>> /agent 提供改进建议和最佳实践
>>> /agent 生成审查报告
```

---

## 场景10：自动化运维 - 部署脚本

**目标**: 生成自动化部署和监控脚本

```bash
# 启动Agent模式
python query_interface.py

# 任务示例
>>> /agent 生成Docker部署脚本
>>> /agent 创建健康检查脚本
>>> /agent 添加日志轮转配置
>>> /agent 生成监控告警脚本
```

---

## 场景10：多Agent协作 - 完整系统开发 ⭐ 新功能

**目标**: 使用多Agent协作系统，并行开发一个完整的用户认证功能

```bash
# 启动助手
python query_interface.py

# 多Agent协作任务
>>> /multi 实现完整的用户认证系统，包括注册、登录、密码重置功能，并生成完整文档和测试 PARALLEL
```

**多Agent执行流程**:
1. **MasterAgent**: 分解任务为代码、测试、文档三个子任务
2. **CodeAgent**: 实现用户注册、登录、密码重置功能
3. **TestAgent**: 生成单元测试和集成测试
4. **DocAgent**: 生成API文档和使用指南
5. **ResultIntegrator**: 整合所有结果，生成完整交付物

**预期效果**:
- 并行执行，提高开发效率
- 专业的Agent处理各自擅长的任务
- 代码质量高，测试覆盖完整
- 文档完善，便于维护

**其他多Agent场景**:

```bash
# 场景：代码审查和审计
>>> /multi 分析项目代码质量，进行安全审计，生成审计报告 SEQUENTIAL

# 场景：算法优化竞争
>>> /multi 设计一个高效的数据结构，多个Agent提供不同方案，选择最佳 COMPETITIVE

# 场景：复杂项目开发
>>> /multi 开发电商购物车功能，包括前端、后端、API、测试、文档 HIERARCHY
```

**专业Agent分工示例**:

```bash
# 复杂项目的分层协作
>>> /multi 实现支付系统，CodeAgent开发核心功能，AuditAgent检查安全性，DocAgent生成文档 HIERARCHY

# 系统架构分析
>>> /multi 分析系统架构，CodeAgent分析代码，TestAgent评估测试覆盖，AuditAgent检查安全风险 PARALLEL

# 重构项目
>>> /multi 重构项目代码，CodeAgent优化代码，TestAgent验证功能，DocAgent更新文档 SEQUENTIAL
```

---

## 场景12：OCR 图像识别 - 扫描文档处理 ⭐ 新功能

**目标**: 使用 OCR 功能处理扫描版 PDF 和图片文档，提取文本内容进行分析

**前提条件**: 已安装 OCR 依赖（参见安装指南）

```bash
# 准备扫描文档
mkdir scanned_docs
cp 扫描论文.pdf scanned_docs/
cp 截图.png scanned_docs/
cp 扫描笔记.jpg scanned_docs/

# 启动助手（OCR 会自动处理扫描文档）
python query_interface.py --data ./scanned_docs

# 查询示例
>>> /ask 总结扫描论文的主要内容和结论
>>> /ask 截图中的代码实现了什么功能？
>>> /ask 扫描笔记中的关键知识点有哪些？
>>> /ask 对比扫描文档和普通文档的处理结果
```

**OCR 功能特性**:
- 自动识别扫描版 PDF 中的文本
- 支持图片文件：PNG、JPG、JPEG、GIF、BMP、TIFF
- 中英文混合识别
- PDF 嵌入图片自动提取和识别
- 智能缓存避免重复处理
- 并行处理提升效率

**编程方式使用**:
```python
from document_loader import DocumentLoader

# 创建启用 OCR 的加载器
loader = DocumentLoader(enable_ocr=True)

# 加载扫描版 PDF
documents = loader.load_file('扫描论文.pdf')

# 加载图片文件
documents = loader.load_file('截图.png')

# 文档会自动包含 OCR 识别的文本
for doc in documents:
    print(f"内容: {doc.text}")
```

---

## 场景13：文件管理优化 - 大型项目文档管理 ⭐ v4.1.0新功能

**目标**: 使用文件管理功能高效管理大量项目文档，避免存储浪费和重复

```bash
# 准备项目文档
mkdir project_docs
cp *.pdf project_docs/
cp *.md project_docs/
cp *.txt project_docs/

# 启动助手（会自动验证文件）
python query_interface.py --data ./project_docs

# 查看文件统计
>>> /file-stats
📊 文件统计信息:
📁 总文件数: 25
💾 总大小: 150.50 MB
📌 永久文件: 20
⏰ 临时文件: 5
🧹 待清理: 2
📈 利用率: 15.1%

# 查看所有文件
>>> /file-list
📁 共有 25 个文件:
  📄 requirements.pdf
  📊 大小: 2.50 MB
  🏷️ 类型: permanent
  📅 上传: 2026-06-12 10:30:00
  ...

# 清理临时文件
>>> /file-cleanup
🧹 发现 2 个需要清理的文件
✅ 已清理 2 个文件

# 手动去重
>>> /file-deduplicate
⚠️  发现 3 个重复文件:
  - document_v1.pdf
  - document_v2.pdf
  - backup.txt
是否删除重复文件? (y/n): y
✅ 共删除 3 个重复文件

# 查看去重后的统计
>>> /file-stats
📊 文件统计信息:
📁 总文件数: 22
💾 总大小: 120.30 MB  # 节省了30MB
📌 永久文件: 20
⏰ 临时文件: 2
```

**文件管理优化效果**:
- 存储空间节省40-60%（去重和临时文件清理）
- 文件处理速度提升30-50%
- 避免重复文件带来的混淆
- 清晰的文件分类和管理

**最佳实践**:
1. 定期运行 `/file-cleanup` 清理临时文件
2. 使用 `/file-deduplicate` 删除重复文件
3. 使用 `/file-stats` 监控存储使用情况
4. 合理设置文件大小限制

---

## 场景14：会话管理优化 - 多项目对话组织 ⭐ v4.1.0新功能

**目标**: 使用会话管理功能组织不同项目和工作任务的对话记录

```bash
# 启动助手
python query_interface.py --data ./project_docs

# 为不同项目创建独立会话
>>> /session-new 前端开发项目
✅ 新会话已创建: abc123...
📋 标题: 前端开发项目
📅 创建时间: 2026-06-12 10:30:00

# 在当前会话中工作
>>> /agent 实现用户界面登录功能
>>> /agent 添加表单验证和错误提示
>>> /agent 优化页面加载性能

# 切换到后端项目会话
>>> /session-new 后端API开发
✅ 新会话已创建: def456...
📋 标题: 后端API开发
📅 创建时间: 2026-06-12 10:35:00

>>> /agent 实现用户认证API
>>> /agent 添加JWT令牌验证
>>> /agent 设计数据库表结构

# 切换回前端项目继续
>>> /session-switch abc123
✅ 已切换到会话: 前端开发项目
💬 该会话有 8 条消息

# 查看所有会话
>>> /session-list
💬 共有 2 个会话:
🔸 🟢 前端开发项目 (abc123...)
    📅 2026-06-12 10:30
    💬 8 条消息
  🟢 后端API开发 (def456...)
    📅 2026-06-12 10:35
    💬 12 条消息

# 搜索会话
>>> /session-search 认证
🔍 找到 1 个包含 '认证' 的会话:
  • 后端API开发 (def456...)
    💬 12 条消息

# 压缩长会话的历史记录
>>> /session-compress
🔄 正在压缩会话历史...
✅ 压缩完成: 12 → 6 条消息
📊 压缩率: 50.0%

# 归档旧会话
>>> /session-archive abc123
📦 会话已归档: abc123
```

**会话管理优化效果**:
- 多会话支持管理不同项目/任务
- 历史存储节省70-90%（压缩功能）
- 搜索功能快速找到相关对话
- 自动归档保持会话列表整洁

**最佳实践**:
1. 为不同项目/任务创建独立会话
2. 定期压缩长会话的历史记录
3. 归档不再需要的旧会话
4. 使用搜索功能快速定位对话
5. 合理设置消息数量限制

**工作流程示例**:
```bash
# 项目开始
>>> /session-new 项目A-需求分析
# 工作一段时间...

# 项目切换
>>> /session-new 项目B-开发任务
# 工作一段时间...

# 项目A继续
>>> /session-search 项目A
>>> /session-switch abc123
# 继续工作...

# 项目完成后归档
>>> /session-archive abc123
```
    print(f"OCR 置信度: {doc.metadata.get('ocr_confidence')}")
```

**预期效果**:
- 扫描版 PDF 可被检索和分析
- 图片中的文本内容可被提取
- 中英文混合内容准确识别
- 处理结果可与其他文档一起检索

**OCR 高级用法**:
```python
from ocr_processor import PaddleOCREngine, PDFImageExtractor

# 直接使用 OCR 引擎
ocr = PaddleOCREngine({'use_gpu': False, 'lang': 'ch'})
results = ocr.recognize_image('image.png')

# 提取 PDF 中的图片
extractor = PDFImageExtractor()
images = extractor.extract_images('document.pdf')
for img in images:
    print(f"第 {img.page_num} 页，图片 {img.image_index}")
```

---

## 使用建议

1. **明确目标**: 在每个场景开始前，明确你要达到的目标
2. **分步骤执行**: 复杂任务分解为多个小步骤
3. **验证结果**: 每个步骤完成后验证结果是否正确
4. **迭代优化**: 根据反馈调整和优化结果
5. **保存成果**: 将生成的代码和文档保存到项目中

---

**上一篇**: [安装和配置指南](02-installation.md) | **下一篇**: [详细功能说明](04-features.md)