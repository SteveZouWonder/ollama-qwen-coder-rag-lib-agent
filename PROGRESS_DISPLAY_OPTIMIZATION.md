# AI 处理过程进度显示优化方案

## 问题分析

### 当前问题
用户在执行 `/ask` 和 `/agent` 命令时，处理过程中看不到详细的进度信息，特别是处理时间较长时，用户可能因为看不到进度而强制终止任务。

### 当前实现

#### /ask 命令进度
- ✅ 添加文档时显示：`🔄 正在添加到知识库...`
- ✅ 检索时显示：`console.status("[bold green]检索知识库...")`
- ❌ 没有详细的检索进度（检索了多少文档、相关性分数等）
- ❌ 没有时间估算
- ❌ 静态状态指示，无动态更新

#### /agent 命令进度
- ✅ 已有 `on_step_callback` 显示步骤进度
- ✅ 已有 `on_confirm_callback` 用于安全确认
- ❌ 显示方式简单（只显示步骤号和简短消息）
- ❌ 没有进度条或百分比
- ❌ 没有时间估算
- ❌ 单步执行时间较长时无反馈

## 优化方案

### 方案 A：基础优化（推荐优先实施）

#### 1. 增强 /ask 命令的进度显示

**改进点**：
- 添加文档时显示更详细的信息（文档数量、类型等）
- 检索时显示检索进度（文档数量、相关性分数范围）
- 添加时间估算（基于历史数据）

**实现方式**：
```python
# 修改 rag_engine.py 的 query_with_sources 方法
def query_with_sources(self, question: str, progress_callback=None) -> dict:
    """查询并返回来源信息"""
    if self.query_engine is None:
        raise RuntimeError("索引未初始化")
    
    if progress_callback:
        progress_callback({"phase": "embedding", "message": "正在生成查询向量..."})
    
    response = self.query_engine.query(question)
    
    if progress_callback:
        progress_callback({"phase": "retrieving", "message": f"检索到 {len(response.source_nodes)} 个相关文档"})
    
    sources = []
    for i, node in enumerate(response.source_nodes):
        if progress_callback:
            progress_callback({
                "phase": "scoring",
                "message": f"评分文档 {i+1}/{len(response.source_nodes)}",
                "current": i+1,
                "total": len(response.source_nodes)
            })
        sources.append({
            "content": node.node.get_content()[:300],
            "score": float(node.score) if hasattr(node, "score") else None,
            "file": node.node.metadata.get("file_name", "未知"),
            "path": node.node.metadata.get("file_path", ""),
        })

    if progress_callback:
        progress_callback({"phase": "generating", "message": "正在生成回答..."})
    
    return {
        "answer": str(response),
        "sources": sources,
    }
```

**修改 query_interface.py**：
```python
def ask_progress_callback(data: dict):
    phase = data.get("phase", "")
    msg = data.get("message", "")
    
    with console.status(f"[bold cyan]{msg}[/bold cyan]"):
        # 根据不同阶段显示不同的状态
        if phase == "embedding":
            time.sleep(0.1)  # 短暂显示
        elif phase == "retrieving":
            time.sleep(0.2)
        elif phase == "scoring":
            current = data.get("current", 0)
            total = data.get("total", 1)
            console.print(f"[dim]正在评分文档 {current}/{total}...[/dim]")
        elif phase == "generating":
            time.sleep(0.1)

# 在 /ask 命令中使用
progress_callback = ask_progress_callback
result = rag_engine.query_with_sources(question, progress_callback=progress_callback)
```

#### 2. 增强 /agent 命令的进度显示

**改进点**：
- 在 `on_step_callback` 中添加进度条
- 显示时间估算
- 显示当前操作的详细信息

**实现方式**：
```python
def on_step_callback(data: dict):
    step = data.get("step", "?")
    total = data.get("total", "?")
    phase = data.get("phase", "?")
    msg = data.get("message", "")

    phase_emoji = {
        "thinking": "[*]",
        "action": "[>]",
        "executing": "[!]",
        "observed": "[=]",
        "blocked": "[X]",
        "rejected": "[-]",
        "final": "[OK]"
    }.get(phase, "[?]")

    if HAS_RICH:
        color = {
            "thinking": "cyan",
            "executing": "yellow",
            "blocked": "red",
            "rejected": "red",
            "final": "green"
        }.get(phase, "white")
        
        # 添加进度条
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
            transient=True
        )
        
        with progress:
            progress.add_task(
                f"[{color}]{phase_emoji} [{step}/{total}] {msg}[/{color}]",
                total=100,
                completed=(step / total) * 100
            )
    else:
        print(f"[{step}/{total}] {phase_emoji} {msg}")
```

#### 3. 添加全局配置选项

**新增配置项**：
```python
# config.py
class Config:
    # 进度显示设置
    SHOW_PROGRESS = os.getenv("SHOW_PROGRESS", "true").lower() == "true"
    PROGRESS_BAR_STYLE = os.getenv("PROGRESS_BAR_STYLE", "rich")  # "rich" or "simple"
    ESTIMATE_TIME = os.getenv("ESTIMATE_TIME", "true").lower() == "true"
```

---

### 方案 B：高级优化（可选实施）

#### 1. 实现流式进度显示

**功能**：
- 使用 Rich 的 `console.status` 实现动态状态更新
- 实时显示当前操作进度
- 支持中断和恢复

**实现方式**：
```python
from rich.console import Console
from rich.status import Status

def query_with_status(self, question: str, console: Console) -> dict:
    """带状态显示的查询"""
    with console.status("[bold cyan]正在生成查询向量...[/bold cyan]"):
        # embedding 阶段
        import time
        time.sleep(0.5)
    
    with console.status("[bold cyan]正在检索相关文档...[/bold cyan]"):
        # 检索阶段
        time.sleep(1.0)
        response = self.query_engine.query(question)
    
    with console.status("[bold cyan]正在生成回答...[/bold cyan]"):
        # 生成阶段
        time.sleep(0.5)
    
    return {"answer": str(response), "sources": []}
```

#### 2. 添加时间估算功能

**功能**：
- 记录历史执行时间
- 基于历史数据估算当前任务剩余时间
- 显示预估完成时间

**实现方式**：
```python
class TimeEstimator:
    def __init__(self):
        self.history = {}
    
    def record_time(self, operation: str, duration: float):
        if operation not in self.history:
            self.history[operation] = []
        self.history[operation].append(duration)
    
    def estimate_time(self, operation: str, steps: int = 1) -> float:
        if operation not in self.history or not self.history[operation]:
            return None
        avg_time = sum(self.history[operation]) / len(self.history[operation])
        return avg_time * steps

# 在 on_step_callback 中使用
def on_step_callback(data: dict):
    # ... 现有代码 ...
    
    if Config.ESTIMATE_TIME:
        estimated = time_estimator.estimate_time(phase, remaining_steps)
        if estimated:
            console.print(f"[dim]预计剩余时间: {estimated:.1f}秒[/dim]")
```

#### 3. 添加详细模式

**功能**：
- 用户可以通过命令或配置启用详细模式
- 显示更详细的技术信息（向量维度、检索参数等）
- 适合调试和高级用户

**实现方式**：
```python
class Config:
    VERBOSE_MODE = os.getenv("VERBOSE_MODE", "false").lower() == "true"

# 在 query_with_sources 中
if Config.VERBOSE_MODE:
    console.print(f"[dim]查询向量维度: {query_embedding.shape}[/dim]")
    console.print(f"[dim]检索参数: top_k={top_k}, similarity={similarity}[/dim]")
```

---

### 方案 C：交互式优化（用户体验改进）

#### 1. 添加取消按钮

**功能**：
- 在进度显示中添加可交互的取消按钮
- 用户可以随时中断长时间运行的任务

**实现方式**：
```python
from rich.prompt import Confirm

def on_step_callback(data: dict):
    # 显示进度
    console.print(f"[{step}/{total}] {msg}")
    
    # 每隔 N 步询问是否继续
    if step % 5 == 0 and step < total:
        if not Confirm.ask("继续执行?", default=True):
            react_engine.stop()
            return
```

#### 2. 添加实时统计信息

**功能**：
- 显示任务执行统计（已用时间、内存使用等）
- 显示检索结果的相关性统计

**实现方式**：
```python
def on_step_callback(data: dict):
    # 显示进度
    # ... 现有代码 ...
    
    if Config.SHOW_STATS:
        elapsed = time.time() - start_time
        console.print(f"[dim]已用时间: {elapsed:.1f}秒[/dim]")
        
        if phase == "observed":
            console.print(f"[dim]检索相关性: {min(scores):.3f} - {max(scores):.3f}[/dim]")
```

---

## 实施建议

### 阶段 1：基础优化（立即实施）
1. ✅ 增强 `/ask` 命令的进度显示（详细文档信息、检索进度）
2. ✅ 增强 `/agent` 命令的进度显示（进度条、时间估算）
3. ✅ 添加全局配置选项（控制进度显示级别）

### 阶段 2：用户体验改进（近期实施）
1. ⏸️ 添加取消按钮（需要更多交互设计）
2. ⏸️ 添加实时统计信息
3. ⏸️ 改进状态显示的视觉效果

### 阶段 3：高级功能（长期考虑）
1. ⏸️ 流式进度显示
2. ⏸️ 时间估算功能
3. ⏸️ 详细模式

---

## 配置示例

### 环境变量配置
```bash
# 启用进度显示
export SHOW_PROGRESS=true

# 进度条样式 (rich/simple)
export PROGRESS_BAR_STYLE=rich

# 启用时间估算
export ESTIMATE_TIME=true

# 启用详细模式
export VERBOSE_MODE=false
```

### 命令行选项
```bash
# 启用详细模式
python query_interface.py --verbose

# 禁用进度显示
python query_interface.py --no-progress

# 设置进度条样式
python query_interface.py --progress-style simple
```

---

## 预期效果

### /ask 命令
**改进前**：
```
🔄 正在添加到知识库...
[bold green]检索知识库... (静态状态)
🤖 回答: ...
```

**改进后**：
```
📄 检测到文件路径: xxx.png
🔄 正在添加到知识库...
✅ 已加载 1 个文档（149 字符）
🔄 正在生成查询向量...
✅ 查询向量生成完成
🔄 正在检索相关文档...
✅ 检索到 5 个相关文档
🔄 正在评分文档 1/5...
🔄 正在评分文档 2/5...
🔄 正在评分文档 3/5...
🔄 正在评分文档 4/5...
🔄 正在评分文档 5/5...
✅ 评分完成 (相关性: 0.75 - 0.92)
🔄 正在生成回答...
🤖 回答: ...
```

### /agent 命令
**改进前**：
```
[*] [1/10] Step 1/10: 模型推理中...
[!] [1/10] Step 1: 执行 read_file...
[=] [1/10] Step 1: read_file 执行完成
```

**改进后**：
```
[*] [1/10] Step 1/10: 模型推理中... [████░░░░░░░░░░] 10%
[!] [1/10] Step 1: 执行 read_file... [████████░░░░░░] 20%
[=] [1/10] Step 1: read_file 执行完成 [██████████░░░░] 30%
[已用时间: 2.3秒] [预计剩余: 20.7秒]
```

---

## 技术考虑

### 性能影响
- 基础优化：对性能影响最小（< 1%）
- 进度条：可能增加少量开销（1-3%）
- 时间估算：需要记录历史数据，占用少量内存

### 兼容性
- Rich 库依赖：进度条需要 Rich 库
- 兜底方案：如果没有 Rich，使用简单的文本进度
- 配置向后兼容：默认行为保持不变

### 可维护性
- 将进度逻辑模块化，便于维护
- 提供配置选项，便于调试
- 添加单元测试，确保功能稳定

---

## 总结

建议优先实施**方案 A（基础优化）**，具体包括：
1. 增强 `/ask` 命令的进度显示
2. 增强 `/agent` 命令的进度显示
3. 添加全局配置选项

这些改进可以显著提升用户体验，同时实施成本较低，不会对系统性能产生显著影响。

如果效果良好，可以考虑逐步实施方案 B 和 C 的功能。