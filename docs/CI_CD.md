# GitHub Actions CI/CD 配置文档

## 概述

本项目配置了完整的GitHub Actions CI/CD流水线，确保代码质量和安全性。

## 触发条件

CI/CD流水线在以下情况下自动触发：

- **推送到master分支**：当代码推送到master分支时自动执行
- **Pull Request到master分支**：当创建或更新PR到master分支时自动执行

## 工作流程

### Job 1: build-and-test

主要构建和测试任务，包括以下步骤：

1. **环境准备**
   - 检出代码
   - 设置Python 3.13环境
   - 缓存pip依赖以加快构建速度
   - 安装项目依赖和开发工具

2. **代码质量检查**
   - **Python语法检查**：使用Python编译器检查所有.py文件的语法正确性
   - **Flake8 Linting**：检查代码风格和潜在错误
   - **Pylint Linting**：深度代码质量分析

3. **安全扫描**
   - **Bandit**：静态代码安全分析，检测常见安全问题
   - **Safety**：检查依赖包中的已知安全漏洞

4. **测试执行**
   - **Pytest**：运行所有单元测试
   - **覆盖率检查**：确保测试覆盖率达到80%以上

5. **报告上传**
   - 上传安全扫描报告到GitHub Artifacts
   - 上传测试覆盖率报告
   - 生成执行摘要

### Job 2: security-scan

专门的安全扫描任务，重点检查依赖包中的关键安全漏洞：

- 检测Critical和High级别的安全漏洞
- 如果发现关键漏洞，工作流程将失败
- 上传详细的安全检查报告

## 检查标准

### 代码质量标准

- ✅ Python语法必须正确（无编译错误）
- ✅ 代码风格符合PEP 8规范（flake8）
- ✅ 代码质量评分≥8.0（pylint）

### 安全标准

- ✅ 无Critical级别的安全漏洞
- ✅ 无High级别的安全漏洞
- ✅ 依赖包无已知安全漏洞

### 测试标准

- ✅ 所有单元测试必须通过
- ✅ 测试覆盖率≥80%
- ✅ 关键功能测试覆盖率≥95%

## 配置文件

### 主要配置文件

- `.github/workflows/ci.yml` - GitHub Actions工作流程定义
- `.flake8` - Flake8代码检查配置
- `.pylintrc` - Pylint代码质量检查配置
- `pytest.ini` - Pytest测试配置

### 本地运行检查

你可以在本地运行相同的检查：

```bash
# 安装开发工具
pip install flake8 pylint bandit safety pytest pytest-cov

# 代码语法检查
python -m py_compile **/*.py

# Flake8检查
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

# Pylint检查
pylint **/*.py --exit-zero --output-format=text

# 安全扫描
bandit -r . -lll -i
safety check

# 运行测试
pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html

# 检查覆盖率
coverage report --fail-under=80
```

## 故障排查

### 常见问题

1. **测试失败**
   - 检查本地测试是否通过：`pytest tests/ -v`
   - 查看测试覆盖率报告：`htmlcov/index.html`

2. **安全漏洞**
   - 查看上传的安全报告Artifacts
   - 运行`safety check`查看详细漏洞信息
   - 更新有漏洞的依赖包

3. **代码风格问题**
   - 运行`flake8 .`查看具体问题
   - 运行`pylint **/*.py`查看详细质量报告

## 自定义配置

### 修改Python版本

编辑`.github/workflows/ci.yml`中的`python-version`矩阵：

```yaml
strategy:
  matrix:
    python-version: ['3.12', '3.13']
```

### 修改覆盖率阈值

编辑`pytest.ini`或GitHub Actions工作流程中的`--cov-fail-under`参数。

### 调整安全检查严格度

编辑`.github/workflows/ci.yml`中的bandit参数：
- `-lll`：低严格度
- `-ll`：中等严格度
- `-l`：高严格度

## 持续改进

CI/CD配置会根据项目需求持续优化：

- 添加更多代码质量检查工具
- 集成性能测试
- 添加自动化部署流程
- 优化构建速度

## 支持

如有问题或建议，请通过以下方式联系：

- 提交Issue到项目仓库
- 创建Pull Request改进CI/CD配置

---

**最后更新**: 2026-06-12
**维护者**: AI Development Team