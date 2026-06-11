# OCR 图片/图表提取功能设计文档

## 功能概述

为现有 RAG 知识库系统添加 OCR（光学字符识别）能力，支持从文档中提取图片和图表的文本内容，使系统能够处理扫描版 PDF、图片文档和包含图表的文档。

## 背景与需求

### 当前限制
- 项目仅支持文本型 PDF，无法处理扫描版 PDF
- 不支持图片格式文档（PNG、JPG、GIF 等）
- 文档中的图表、截图等视觉信息无法被索引和检索

### 用户需求
- 学术研究者需要处理扫描版论文
- 技术文档常包含截图和架构图
- 财务/报表文档包含大量图表数据
- 中文文档 OCR 支持是核心需求

## 技术选型

### OCR 引擎对比

| 引擎 | 优势 | 劣势 | 适用场景 |
|------|------|------|----------|
| **PaddleOCR** | 中文识别准确率高、轻量级、免费 | 对复杂表格支持一般 | **首选：中英文混合文档** |
| Tesseract | 开源标准、支持多语言、生态成熟 | 中文识别准确率较低 | 英文为主的多语言文档 |
| EasyOCR | 易用性好、基于 PyTorch | 模型较大、速度较慢 | 快速原型开发 |
| Qwen2-VL | 理解图表语义、多模态能力 | 需要额外模型部署 | **未来：复杂图表理解** |

### 推荐方案：PaddleOCR + Tesseract 混合

**主要引擎：PaddleOCR**
- 中文识别准确率达 95%+
- 支持方向检测和倾斜校正
- 提供表格识别模型
- 轻量级，CPU 即可运行

**备用引擎：Tesseract**
- 作为 PaddleOCR 的后备方案
- 处理纯英文文档时效率更高
- 支持更多特殊语言（日语、韩语等）

### 依赖库

```txt
# OCR 核心
paddlepaddle>=2.5.0          # PaddlePaddle 深度学习框架
paddleocr>=2.7.0             # PaddleOCR 工具包
pytesseract>=0.3.10          # Tesseract Python 绑定

# 图像处理
pillow>=10.0.0               # 图像读写和处理
opencv-python>=4.8.0         # 图像预处理（可选）

# PDF 图像提取
pymupdf>=1.23.0              # 从 PDF 提取图片
```

## 功能设计

### 1. 支持的文档类型

| 文档类型 | 处理方式 |
|----------|----------|
| 扫描版 PDF | 逐页 OCR 识别 |
| 图片文件（PNG/JPG） | 直接 OCR 识别 |
| 混合型 PDF | 文本提取 + 图片提取 + OCR |
| Markdown | 提取嵌入的图片链接并处理 |
| 网页截图 | 直接 OCR 识别 |

### 2. 核心功能模块

```
ocr_processor/
├── base.py              # OCR 抽象基类
├── paddle_ocr.py        # PaddleOCR 实现
├── tesseract_ocr.py     # Tesseract 实现
├── image_extractor.py   # 从 PDF 提取图片
├── preprocessor.py      # 图像预处理
└── cache.py             # OCR 结果缓存
```

### 3. 处理流程

```
文档输入
    ↓
格式检测
    ↓
┌─────────────┬─────────────┬─────────────┐
│   PDF       │   图片      │  Markdown   │
└─────────────┴─────────────┴─────────────┘
    ↓            ↓            ↓
图片提取    图像预处理    图片链接解析
    ↓            ↓            ↓
图像预处理    ↓            ↓
    ↓            ↓            ↓
    └────────────┼────────────┘
                 ↓
            OCR 识别
                 ↓
            后处理（去噪、格式化）
                 ↓
            缓存结果
                 ↓
            返回结构化数据
```

## 性能优化策略

### 1. 异步处理
- 使用线程池并行处理多页/多图
- 大文件分批次处理，避免内存溢出

### 2. 智能缓存
- 基于文件哈希的缓存机制
- 缓存 OCR 结果避免重复处理
- 支持缓存过期和手动清理

### 3. 增量处理
- 仅处理新增或修改的文件
- 支持断点续传

### 4. 资源控制
- 限制并发 OCR 任务数量
- 内存使用监控和限制
- CPU 使用率控制

## 集成方案

### 与现有系统集成

1. **扩展 DocumentLoader**
   - 在 `document_loader.py` 中添加图片格式支持
   - 添加 OCR 处理钩子

2. **修改配置**
   - 在 `config.py` 中添加 OCR 配置项
   - 支持 OCR 引擎选择和参数调优

3. **更新索引流程**
   - OCR 结果与原文本合并
   - 保留图片位置元数据

### 配置项设计

```python
# OCR 配置
OCR_ENGINE = os.getenv("OCR_ENGINE", "paddle")  # paddle | tesseract | hybrid
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() == "true"
OCR_CACHE_DIR = INDEX_DIR / "ocr_cache"
OCR_PARALLEL_WORKERS = int(os.getenv("OCR_PARALLEL_WORKERS", "2"))
OCR_TIMEOUT = int(os.getenv("OCR_TIMEOUT", "60"))

# PaddleOCR 特定配置
PADDLE_USE_GPU = os.getenv("PADDLE_USE_GPU", "false").lower() == "true"
PADDLE_LANG = os.getenv("PADDLE_LANG", "ch")  # ch | en | jk

# Tesseract 特定配置
TESSERACT_PATH = os.getenv("TESSERACT_PATH", "/usr/local/bin/tesseract")
TESSERACT_LANG = os.getenv("TESSERACT_LANG", "chi_sim+eng")
```

## 实施阶段

### Phase 1: 基础 OCR 能力（1-2 周）
- [ ] 集成 PaddleOCR 基础功能
- [ ] 实现图片文件 OCR 处理
- [ ] 添加 OCR 结果缓存
- [ ] 编写单元测试

### Phase 2: PDF 图片提取（1 周）
- [ ] 实现从 PDF 提取图片
- [ ] 添加图片位置信息
- [ ] 实现混合型 PDF 处理
- [ ] 性能优化

### Phase 3: 高级功能（1-2 周）
- [ ] 添加 Tesseract 作为备用引擎
- [ ] 实现图像预处理（去噪、倾斜校正）
- [ ] 添加表格识别
- [ ] Markdown 嵌入图片处理

### Phase 4: 集成与优化（1 周）
- [ ] 与现有 DocumentLoader 集成
- [ ] 添加 CLI 命令支持
- [ ] 性能优化和压力测试
- [ ] 文档完善

## 风险与挑战

### 技术风险
1. **OCR 准确率**：复杂表格、手写文字识别率可能较低
   - 缓解：提供人工校正接口

2. **性能问题**：OCR 是 CPU 密集型操作，处理大文件耗时
   - 缓解：异步处理、智能缓存、增量更新

3. **依赖兼容性**：PaddlePaddle 与现有依赖可能冲突
   - 缓解：使用虚拟环境、版本锁定

### 资源需求
- **CPU**: 推荐 4 核心以上
- **内存**: 推荐 8GB 以上
- **磁盘**: OCR 缓存需要额外空间（约原文件 2-3 倍）

## 成功指标

- **准确率**: 中文识别准确率 >90%
- **性能**: 单页 PDF OCR 处理 <3 秒
- **兼容性**: 与现有系统 100% 兼容
- **稳定性**: 连续处理 1000 页无崩溃

## 未来扩展

### 多模态理解
- 集成 Qwen2-VL 等视觉-语言模型
- 理解图表语义（如趋势图、架构图）
- 生成图表描述

### 表格结构化
- 识别表格结构
- 提取表格数据为 JSON/CSV
- 支持表格查询

### 手写识别
- 支持手写文字识别
- 适用于笔记、批注等场景
