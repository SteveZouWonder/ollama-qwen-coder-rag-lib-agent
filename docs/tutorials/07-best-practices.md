# 最佳实践指南

> 本文档提供使用智能文档+代码助手的最佳实践和建议。

---

## 1. 知识库管理

### 文档组织

**推荐结构**:
```
data/
├── papers/          # 论文文档
├── docs/            # 技术文档
├── code/            # 代码文件
└── notes/           # 笔记文档
```

**建议**:
- 按主题分类文档
- 使用清晰的文件命名
- 定期清理过期文档
- 保持文档结构一致

### 分块策略

**根据文档类型调整分块**:
```python
# 论文文档：较大分块
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 200

# 代码文件：较小分块
CHUNK_SIZE = 512
CHUNK_OVERLAP = 100

# 配置文件：最小分块
CHUNK_SIZE = 256
CHUNK_OVERLAP = 50
```

### 索引优化

**增量更新**:
```python
# 不要每次都重建索引
# 使用增量更新功能
from knowledge_snapshot import create_snapshot

# 创建快照
create_snapshot("论文快照", "./papers")

# 后续更新
update_snapshot("论文快照", "./new_papers")
```

---

## 2. Agent任务设计

### 任务分解

**将复杂任务分解为小步骤**:
```bash
# ❌ 不好的做法
>>> /agent 重构整个项目，优化性能，添加测试，生成文档

# ✅ 好的做法
>>> /agent 分析项目结构，识别需要重构的模块
>>> /agent 重构数据处理模块
>>> /agent 为重构的模块添加单元测试
>>> /agent 运行测试验证功能
>>> /agent 更新相关文档
```

### 明确目标

**提供清晰的任务描述**:
```bash
# ❌ 不清晰的描述
>>> /agent 优化代码

# ✅ 清晰的描述
>>> /agent 优化utils.py中的数据处理函数，减少内存使用，保持功能不变
```

### 设置限制

**合理设置资源限制**:
```python
# 在配置中设置
MAX_ITERATIONS = 30  # 限制迭代次数
TIMEOUT = 300        # 设置超时
MAX_HISTORY = 50     # 限制历史长度
```

---

## 3. 安全使用

### 命令确认

**始终启用命令确认**:
```python
# 配置中确保
CODE_AGENT_AUTO_CONFIRM = False
```

### 数据保护

**保护敏感信息**:
```bash
# 不要将敏感信息放入知识库
# 使用环境变量存储密钥
export API_KEY="your-key"

# 在.env文件中设置
echo 'API_KEY=your-key' >> .env
chmod 600 .env
```

### 操作范围

**限制Agent操作范围**:
```bash
# 在特定目录中工作
cd /path/to/project
python query_interface.py

# 使用相对路径
>>> /agent 处理当前目录的文件
```

---

## 4. 性能优化

### 模型选择（按机器与使用场景）

默认模型 `qwen3.5:4b`（"协同档"）在 16GB 内存机器上、与 IDE/浏览器同时运行时仍能全 GPU 驻留
（16K 上下文实测约 3.7GB）。运行中可用 CLI `/model <name>` 或 Web 对话页的模型下拉热切换，
旧模型会被立即释放。

| 场景 | 内存 | 推荐模型 | 说明 |
|---|---|---|---|
| 日常助手，与 IDE/浏览器并行（默认） | 16GB | `qwen3.5:4b` | 约 3.7GB 驻留，本机 M4 实测 ~25 tok/s |
| 专注模式 / 复杂重构 / 多步 Agent | 16GB（关闭 IDE）或 32GB | `qwen3.5:9b` | 约 6GB 驻留，~16 tok/s；工具调用（BFCL 66 vs 50）与代码能力明显更强 |
| 低配 / 老机器 | 8GB | `qwen3.5:2b` | 约 1.9GB，适合问答与检索 |
| 工作站 | 32GB+ 或 24GB 显卡 | `qwen3.5:27b` / `gemma4:26b` | 17~19GB |
| 严格格式化输出 / 翻译为主，不依赖工具调用 | 16GB（关闭 IDE） | `gemma4:12b-it-qat` | 指令遵循最强，但工具调用偏弱 |
| Embedding（所有场景） | — | `nomic-embed-text:latest` | 固定 |

```bash
# 启动时指定
python src/query_interface.py --model qwen3.5:9b
# 或环境变量
export LLM_MODEL=qwen3.5:9b
# 运行中热切换（CLI）
/model list
/model qwen3.5:9b
# 运行中开关思考模式（CLI）
/think on
/think off
```

**与 IDE 共存的内存实践**
- 项目默认关闭思考模式（`LLM_THINK=false`）：同一问题 qwen3.5:4b 从 31s 降到 2.8s；需要深度推理时可运行中开启——CLI `/think on`（`/think off` 关闭、`/think` 查看），Web 对话页勾选「思考模式」；仅支持思考的模型（qwen3.5 等）可开启，不支持时会被拒绝并提示。
- 桌面应用默认不在启动时预热模型（`warm_up_on_startup: false`），Ollama 会在首次请求时按需加载、闲置 5 分钟后释放；可设 `OLLAMA_KEEP_ALIVE=2m` 更快归还内存。
- 上下文按模型自动推导（4B→16K，7~9B→8K，12B+→4K）；每 +16K 约多占 0.6GB，长文档任务可临时 `LLM_NUM_CTX=32768`。
- 切换模型时项目会主动释放旧模型；若用 `ollama run` 手动加载过其他模型，用 `/model` 查看并 `ollama stop <name>` 释放。

**关注中（暂不推荐）**：`SparkLLM/Spark-X2.5-4B` 在同尺寸模型中 Agent/代码基准领先，但官方 Ollama 尚不支持其 `spark2_5` 架构（llama.cpp PR #27868 进行中，需自编译运行时且仅有 8.2GB 未量化版本）。待上游合入并提供量化 tag 后再评估。

### 查询优化

**提高查询效率**:
```python
# 减少返回结果数量
TOP_K = 3  # 而不是 5

# 设置相似度阈值
SIMILARITY_CUTOFF = 0.8  # 而不是 0.7

# 使用缓存
ENABLE_CACHE = True
```

### 资源管理

**合理使用系统资源**:
```bash
# 定期清理缓存
rm -rf index_storage/cache/*

# 清理日志
find logs/ -name "*.log" -mtime +7 -delete

# 监控资源使用
htop  # Linux
top   # macOS
```

---

## 5. 集成到工作流

### 自动化脚本

**创建自动化脚本**:
```bash
#!/bin/bash
# daily_check.sh

# 预热模型
python desktop_app.py --warm-up

# 检查服务状态
python desktop_app.py --status >> daily_status.log

# 运行测试
python -m pytest tests/
```

### 定时任务

**使用cron设置定时任务**:
```bash
# 编辑crontab
crontab -e

# 每天早上9点预热模型
0 9 * * * cd /path/to/project && python desktop_app.py --warm-up

# 每6小时检查服务状态
0 */6 * * * cd /path/to/project && python desktop_app.py --status
```

### CI/CD集成

**在CI/CD流水线中使用**:
```yaml
# .github/workflows/test.yml
name: Test

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        run: |
          python -m pytest tests/
      - name: Code review
        run: |
          python query_interface.py --agent "审查src/目录的代码"
```

---

## 6. 团队协作

### 配置共享

**使用版本控制管理配置**:
```bash
# 提交配置文件
git add config/.env.example
git commit -m "Add config example"

# 不提交实际配置
echo ".env" >> .gitignore
echo "index_storage/" >> .gitignore
```

### 文档协作

**建立文档规范**:
- 统一文件命名规范
- 使用模板文档
- 定期更新文档
- 建立文档审查机制

### 知识共享

**建立知识库共享**:
```bash
# 共享团队知识库
python query_interface.py --data ./team_docs

# 定期同步知识库
git pull origin main
python query_interface.py --data ./team_docs
```

---

## 7. 监控和维护

### 日志管理

**定期查看和分析日志**:
```bash
# 查看错误日志
grep ERROR logs/*.log

# 查看性能日志
grep PERFORMANCE logs/*.log

# 日志轮转
logrotate /etc/logrotate.d/ollama-assistant
```

### 性能监控

**监控系统性能**:
```bash
# 监控内存使用
watch -n 5 'free -h'

# 监控磁盘使用
watch -n 5 'df -h'

# 监控进程状态
watch -n 5 'ps aux | grep python'
```

### 定期维护

**执行定期维护任务**:
```bash
#!/bin/bash
# maintenance.sh

# 清理缓存
rm -rf index_storage/cache/*

# 清理旧日志
find logs/ -name "*.log" -mtime +30 -delete

# 更新依赖
pip install --upgrade -r requirements.txt

# 检查系统状态
python desktop_app.py --status
```

---

## 8. 故障恢复

### 备份策略

**定期备份重要数据**:
```bash
# 备份知识库索引
tar -czf index_backup_$(date +%Y%m%d).tar.gz index_storage/

# 备份配置
tar -czf config_backup_$(date +%Y%m%d).tar.gz config/

# 备份日志
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs/
```

### 恢复流程

**制定恢复流程**:
1. 停止应用
2. 恢复配置文件
3. 恢复知识库索引
4. 验证服务状态
5. 重启应用

---

## 9. 持续改进

### 收集反馈

**定期收集使用反馈**:
- 记录常见问题
- 统计使用频率
- 收集用户建议
- 分析性能数据

### 优化迭代

**基于反馈进行优化**:
- 优化常用功能
- 修复已知问题
- 改进用户体验
- 更新文档

### 学习提升

**持续学习和提升**:
- 关注新技术发展
- 参与社区讨论
- 分享使用经验
- 贡献代码和文档

---

## 10. 常见错误避免

### 避免的错误

1. **不使用虚拟环境**
   - 导致依赖冲突
   - 影响系统Python环境

2. **忽略错误日志**
   - 错过重要信息
   - 问题积累

3. **过度依赖AI**
   - 不审查生成代码
   - 盲目执行建议

4. **不备份重要数据**
   - 数据丢失风险
   - 无法恢复

5. **忽略安全最佳实践**
   - 敏感信息泄露
   - 系统安全风险

### 推荐做法

1. **始终使用虚拟环境**
2. **定期查看日志**
3. **审查AI生成的内容**
4. **定期备份数据**
5. **遵循安全最佳实践**

---

通过遵循这些最佳实践，你可以更有效地使用智能文档+代码助手，提高工作效率，减少常见问题，确保系统的稳定性和安全性。

---

**上一篇**: [故障排除](06-troubleshooting.md) | **返回目录**: [TUTORIAL.md](../TUTORIAL.md)