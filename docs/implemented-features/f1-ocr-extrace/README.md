# OCR 图片/图表提取功能 - 设计文档

## 概述

本文档集包含为 RAG 知识库系统添加 OCR（光学字符识别）功能的完整设计方案。该功能将使系统能够处理扫描版 PDF、图片文档和包含图表的文档。

## 文档索引

### 1. [OVERVIEW.md](./OVERVIEW.md) - 功能概述与技术选型
- 功能背景与需求分析
- OCR 引擎对比（PaddleOCR vs Tesseract vs EasyOCR）
- 技术选型推荐：PaddleOCR + Tesseract 混合方案
- 功能设计范围
- 性能优化策略
- 实施阶段规划
- 风险分析与成功指标

### 2. [ARCHITECTURE.md](./ARCHITECTURE.md) - 系统架构设计
- 整体系统架构图
- 模块详细设计
  - OCR 核心模块（BaseOCREngine、PaddleOCREngine、TesseractOCREngine）
  - 图片提取器（PDFImageExtractor）
  - OCR 缓存系统（OCRCache）
- DocumentLoader 扩展设计
- 数据流设计
- 配置管理方案
- 错误处理策略
- 性能优化实现

### 3. [IMPLEMENTATION.md](./IMPLEMENTATION.md) - 实现指南
- Phase 1: 环境准备（依赖安装、验证）
- Phase 2: 实现 OCR 核心模块（代码示例）
- Phase 3: 扩展 DocumentLoader（集成步骤）
- Phase 4: 扩展配置系统
- Phase 5: 添加单元测试
- Phase 6: 集成测试
- Phase 7: 性能优化
- Phase 8: 文档和部署
- 验收标准
- 常见问题解答

### 4. [TESTING.md](./TESTING.md) - 测试策略
- 测试目标与分层
- 单元测试（OCR 引擎、缓存、图片提取器）
- 集成测试（DocumentLoader 集成、端到端流程）
- 性能测试（处理时间、吞吐量、内存使用）
- 准确性测试（中文、英文识别率）
- 稳定性测试（长时间运行、大批量处理）
- 测试数据准备
- 测试执行与报告
- 测试通过标准

## 技术方案摘要

### 核心技术栈
- **OCR 引擎**: PaddleOCR（主要）+ Tesseract（备用）
- **图像处理**: OpenCV + Pillow
- **PDF 处理**: PyMuPDF (fitz)
- **深度学习框架**: PaddlePaddle

### 主要特性
- ✅ 支持扫描版 PDF OCR
- ✅ 支持图片文件（PNG、JPG、JPEG、GIF、BMP、TIFF）
- ✅ 中英文混合识别
- ✅ 智能缓存避免重复处理
- ✅ 异步并行处理提升性能
- ✅ 可配置的 OCR 引擎选择
- ✅ PDF 图片自动提取与 OCR

### 性能目标
- 单张图片处理时间 <3 秒
- 中文识别准确率 >90%
- 英文识别准确率 >95%
- 批量处理吞吐量 >10 图片/分钟

## 实施路线图

```
Phase 1: 环境准备      [1-2 天]
  ├─ 安装依赖
  ├─ 验证安装
  └─ 创建模块目录

Phase 2: 核心模块      [1-2 周]
  ├─ 实现 OCR 基类
  ├─ 实现 PaddleOCR
  ├─ 实现 Tesseract
  ├─ 实现图片提取器
  └─ 实现缓存系统

Phase 3: 系统集成      [1 周]
  ├─ 扩展 DocumentLoader
  ├─ 扩展配置系统
  └─ 集成测试

Phase 4: 优化与部署    [1 周]
  ├─ 性能优化
  ├─ 编写文档
  └─ 部署脚本

总计: 约 3-4 周
```

## 快速开始

### 1. 阅读顺序建议
```
新手: OVERVIEW → IMPLEMENTATION → TESTING
架构师: OVERVIEW → ARCHITECTURE → IMPLEMENTATION
测试工程师: TESTING → OVERVIEW → IMPLEMENTATION
```

### 2. 环境准备
```bash
# 安装核心依赖
pip install paddlepaddle==2.5.2
pip install paddleocr==2.7.0.3
pip install pymupdf==1.23.8
pip install opencv-python==4.8.1.78
pip install pytesseract==0.3.10

# 安装 Tesseract（系统级）
# macOS
brew install tesseract
# Linux
sudo apt-get install tesseract-ocr
```

### 3. 验证安装
```python
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_angle_cls=True, lang="ch")
print("✅ PaddleOCR 安装成功")
```

## 目录结构

实现后的目录结构：
```
ollama-qwen-coder-rag-lib-agent/
├── ocr_processor/
│   ├── __init__.py
│   ├── base.py              # OCR 抽象基类
│   ├── paddle_ocr.py        # PaddleOCR 实现
│   ├── tesseract_ocr.py     # Tesseract 实现
│   ├── image_extractor.py   # PDF 图片提取器
│   ├── preprocessor.py      # 图像预处理
│   └── cache.py             # OCR 结果缓存
├── document_loader.py       # 扩展支持 OCR
├── config.py               # 扩展 OCR 配置
├── tests/
│   ├── test_ocr_processor.py
│   ├── test_ocr_cache.py
│   ├── test_image_extractor.py
│   ├── test_ocr_integration.py
│   ├── test_ocr_e2e.py
│   ├── test_ocr_performance.py
│   ├── test_ocr_accuracy.py
│   └── test_ocr_stability.py
└── docs/future-feature-design/f1-ocr-extrace/
    ├── README.md           # 本文件
    ├── OVERVIEW.md
    ├── ARCHITECTURE.md
    ├── IMPLEMENTATION.md
    └── TESTING.md
```

## 配置示例

在 `config.py` 中添加：
```python
# OCR 配置
OCR_ENABLED = True
OCR_ENGINE = "paddle"  # paddle | tesseract | hybrid
OCR_CACHE_DIR = INDEX_DIR / "ocr_cache"
OCR_PARALLEL_WORKERS = 2

# PaddleOCR 配置
PADDLE_USE_GPU = False
PADDLE_LANG = "ch"  # ch | en | jk

# Tesseract 配置
TESSERACT_PATH = "/usr/local/bin/tesseract"
TESSERACT_LANG = "chi_sim+eng"
```

## 使用示例

```python
from document_loader import DocumentLoader

# 创建加载器（启用 OCR）
ocr_config = {
    'enabled': True,
    'engine': 'paddle',
    'use_gpu': False,
    'lang': 'ch',
    'cache_dir': './index_storage/ocr_cache',
}
loader = DocumentLoader(ocr_config=ocr_config)

# 加载图片文件
documents = loader.load_file('scanned_page.png', enable_ocr=True)

# 加载 PDF（自动提取图片并 OCR）
documents = loader.load_file('document_with_images.pdf', enable_ocr=True)
```

## 已知限制

1. **手写文字识别**: 当前方案对印刷文字效果较好，手写文字识别准确率较低
2. **复杂表格**: 复杂表格结构识别可能不准确，未来可考虑专用表格识别模型
3. **GPU 支持**: 默认使用 CPU，GPU 支持需要额外配置 CUDA 环境
4. **大文件处理**: 超大 PDF 文件可能需要分批处理以避免内存溢出

## 未来扩展

- [ ] 表格结构化识别
- [ ] 手写文字识别
- [ ] 集成多模态模型（Qwen2-VL）
- [ ] OCR 结果人工校正界面
- [ ] 支持 WebP、SVG 等更多图片格式
- [ ] 图表语义理解（趋势图、架构图）
- [ ] 数学公式识别

## 贡献指南

如需对设计文档提出改进建议：
1. 在相应文档中提出问题或建议
2. 更新相关章节
3. 保持文档与实现同步

## 联系方式

如有问题或建议，请通过项目 Issue 跟踪系统反馈。

---

**文档版本**: v1.0
**最后更新**: 2026-06-10
**状态**: 设计阶段，待实施
