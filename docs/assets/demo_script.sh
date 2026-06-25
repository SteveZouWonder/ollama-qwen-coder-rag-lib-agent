#!/usr/bin/env bash
# Cerebro 演示脚本（用于生成 README 顶部的 demo.gif）
# 模拟真实 CLI 交互的视觉效果：拖入 PDF -> 提问 -> Agent 自动改代码跑测试
# 注意：此脚本仅用于生成宣传 GIF，输出为预设演示内容，非实时 LLM 推理。
#
# 重新生成 demo.gif（需要 asciinema + agg：brew install asciinema agg）：
#   TERM=xterm-256color asciinema rec --overwrite --cols 110 --rows 32 \
#       --command "bash docs/assets/demo_script.sh" docs/assets/demo.cast
#   agg --theme asciinema --font-size 20 --cols 110 --rows 32 \
#       docs/assets/demo.cast docs/assets/demo.gif
#   rm docs/assets/demo.cast

set -u

# ── 颜色 ──
C_RESET=$'\033[0m'
C_DIM=$'\033[2m'
C_CYAN=$'\033[36m'
C_GREEN=$'\033[32m'
C_YELLOW=$'\033[33m'
C_MAGENTA=$'\033[35m'
C_BOLD=$'\033[1m'

type_line() { printf "%s\n" "$1"; sleep "${2:-0.3}"; }

clear

# ── Banner ──
printf "%s" "$C_CYAN$C_BOLD"
cat <<'BANNER'
   ____                _
  / ___|___ _ __ ___ | |__  _ __ ___
 | |   / _ \ '__/ _ \| '_ \| '__/ _ \
 | |__|  __/ | |  __/| |_) | | | (_) |
  \____\___|_|  \___||_.__/|_|  \___/   🧠
BANNER
printf "%s" "$C_RESET"
type_line "${C_DIM}  你的第二大脑 + 代码助手  ·  100% 本地运行  ·  零 API 费用${C_RESET}" 0.6

# ── 模式一：RAG 知识库 ──
type_line ""
type_line "${C_GREEN}>>>${C_RESET} ${C_BOLD}/add ./papers/attention.pdf${C_RESET}" 0.5
type_line "${C_DIM}  [OCR] 检测扫描页 ... 识别中 ✓${C_RESET}" 0.4
type_line "${C_DIM}  [索引] 切分 42 块 -> 向量化 -> 写入 ChromaDB ✓${C_RESET}" 0.6
type_line "${C_GREEN}  已添加 1 个文档到知识库 📚${C_RESET}" 0.5

type_line ""
type_line "${C_GREEN}>>>${C_RESET} ${C_BOLD}/ask 这篇论文的核心贡献是什么？${C_RESET}" 0.6
type_line "${C_DIM}  语义检索 top-5 片段 ...${C_RESET}" 0.5
type_line "  提出 ${C_BOLD}Transformer${C_RESET} 架构，完全基于自注意力机制，"
type_line "  摒弃循环与卷积，实现更强的并行能力与长程依赖建模。"
type_line "${C_DIM}  来源: attention.pdf (相似度 0.91)${C_RESET}" 0.7

# ── 模式二：ReAct Agent ──
type_line ""
type_line "${C_MAGENTA}>>>${C_RESET} ${C_BOLD}/agent 写一个快速排序到 sort.py 并运行测试${C_RESET}" 0.6
type_line "${C_DIM}  [1/6] 模型推理中 ...${C_RESET}" 0.4
type_line "${C_YELLOW}  [2/6] write_file -> sort.py ✓${C_RESET}" 0.4
type_line "${C_YELLOW}  [3/6] write_file -> test_sort.py ✓${C_RESET}" 0.4
type_line "${C_DIM}  [4/6] 模型推理中 ...${C_RESET}" 0.4
type_line "${C_YELLOW}  [5/6] execute_command -> pytest test_sort.py${C_RESET}" 0.5
type_line "${C_GREEN}        ===== 3 passed in 0.04s =====${C_RESET}" 0.5
type_line "${C_GREEN}  [OK] [6/6] 已完成：快速排序实现 + 测试全部通过 ✅${C_RESET}" 0.7

# ── 模式三：多 Agent 协作 ──
type_line ""
type_line "${C_CYAN}>>>${C_RESET} ${C_BOLD}/multi 实现用户登录功能并生成测试与文档 PARALLEL${C_RESET}" 0.6
type_line "${C_DIM}  MasterAgent 分解任务 -> 3 个子任务并行调度${C_RESET}" 0.5
type_line "${C_YELLOW}  ⚙ CodeAgent  -> auth.py        ✓${C_RESET}" 0.35
type_line "${C_YELLOW}  ⚙ TestAgent  -> test_auth.py   ✓${C_RESET}" 0.35
type_line "${C_YELLOW}  ⚙ DocAgent   -> auth.md         ✓${C_RESET}" 0.35
type_line "${C_GREEN}  ResultIntegrator 整合完成：代码 + 测试 + 文档一次交付 🤝${C_RESET}" 0.8

type_line ""
type_line "${C_DIM}  数据全程不出本机 · 隐私优先 · github.com/SteveZouWonder/...${C_RESET}" 1.2
