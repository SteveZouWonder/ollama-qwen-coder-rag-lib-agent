# 调试流程

从现象到修复的固定步骤，配合 [TRAP_AVOIDANCE.md](TRAP_AVOIDANCE.md)（高频根因）与 [TESTING_GUIDELINES.md](TESTING_GUIDELINES.md)（复现 / 隔离手段）。

## 1. 收集现象

- 入口是哪一端：CLI（`python src/query_interface.py`）/ Web（`python src/web/app.py`）/ 桌面（`launcher.py`）/ 打包版？三端共用编排层，但接线不同。
- 模式：自动 / RAG / 单 Agent / 多 Agent？自动模式先确认 `intent_router` 路由到了哪（Web 状态行「实际模式」、CLI 提示）。
- 拿到原始输出：CLI 用 `/summary`（ReAct 步骤日志）、`/context`（会话上下文指标）、`/sources`；Web 看「处理过程」「引用来源」面板与状态行。
- 日志：`logs/`（打包版在用户数据目录）；`logging` 级别 `info` 记录迁移 / 加载 / 切模型，`warning` 记录降级。

## 2. 定位层

```
现象                          先查
─────────────────────────────  ──────────────────────────────────────────────
回答"记得"别的会话 / 上下文乱    conversation_context（单例钉死？carry？session_state？）
Agent 声称做了但没做            step_log 是否有 write_file / execute_command；子 Agent unverified 标记
Agent 死循环 / 步数耗尽         _check_repeat、_forced_summary、Observation 是否过长被折叠
工具"不存在" / 参数错           registry.get_descriptions 输出 vs prompts/system/PROJECT_RULES.md
知识库明明有却"无相关内容"      SIMILARITY_CUTOFF vs KB_RELEVANCE_THRESHOLD、rerank 判定、is_meta_query
联网没结果                      WEB_SEARCH_* 配置、search_cache、各引擎降级日志
数据"消失"                      runtime_paths 解析结果（app_state_dir / user_data_dir）、是否迁移
打包版行为与源码不同            resource_root() 下是否有该资源（datas）、collect_all
Web 界面报 outputs 数量错误      handler 返回元组 vs outputs 列表（ui/*.py）
```

快速打印诊断：

```bash
venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, 'src')
import json, prompt_assets, runtime_paths
print(json.dumps(prompt_assets.describe(), ensure_ascii=False, indent=1))
print(runtime_paths.user_data_dir(), runtime_paths.app_state_dir("knowledge"))
from react_engine import build_system_prompt
from conversation_context import estimate_tokens
p = build_system_prompt(); print(len(p), estimate_tokens(p))
EOF
```

## 3. 复现为测试

- 在对应 `tests/test_<module>.py` 写一个**当前会失败**的测试；用 §5（TESTING_GUIDELINES）的注入手段隔离 LLM / 网络 / 文件。
- 会话类 bug：用 `SessionManager(tmp)` + `ConversationContext(complete=lambda p: "摘要")` 完整走一遍用户操作序列（record → compact → new_session → switch → record），断言每一步落到哪个会话。
- ReAct 类 bug：monkeypatch `ReActEngine._call_model` 返回脚本化响应序列，断言 `step_log` phase 与最终答案前缀。
- Web 类 bug：`build_handlers(MagicMock())` 直接调 handler，断言返回元组；服务层用 `WebService(...factory)`。

## 4. 修复

- 只修根因；相邻同类隐患顺手修并在提交说明中列出。
- 改默认路径 / 持久化格式 → 带迁移；改事件字段 / 返回结构 → 同步三端消费者与测试；改工具签名 → 同步 `prompts/` 与文档。
- 跑相关文件 → 全量 `python -m pytest tests -q --no-cov` → 带覆盖率。

## 5. 记录

- CHANGELOG `[Unreleased]` `修复`：现象 + 根因 + 现行行为（用户可感知的措辞）。
- 若是一类模式，补 `TRAP_AVOIDANCE.md` 一行。
- 提交信息 `fix(scope): …`；询问用户是否创建 PR。

## 6. 常用检查命令

```bash
python -m pytest tests --collect-only -q | tail -1                 # 收集是否有 error
python -m pytest tests/test_x.py -q --no-cov -k "关键字" -vv        # 单测详细输出
python -m pytest tests -q --no-cov -x -p no:cacheprovider          # 首败即停
git status --short                                                 # 测试是否污染了 .cerebro/ index_storage/
grep -rn "旧名" src tests docs prompts                              # 改名后残留
bash scripts/verify_deps.sh                                        # 依赖
```
