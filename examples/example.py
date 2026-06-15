"""
示例脚本：融合 RAG + Agent 快速上手
"""
import sys
from pathlib import Path

# 添加 src 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rag_engine import build_knowledge_base
from react_engine import ReActEngine
from agent_tools import set_rag_engine

print("=" * 60)
print("🚀 示例：融合 RAG 知识库 + ReAct Agent")
print("=" * 60)

# 1. 构建知识库
print("\n📚 步骤1: 构建知识库")
engine = build_knowledge_base("./data")

# 2. 将 RAG 引擎注入 Agent 工具
set_rag_engine(engine)

# 3. 查看统计
print("\n📊 步骤2: 知识库统计")
stats = engine.get_stats()
for k, v in stats.items():
    print(f"   {k}: {v}")

# 4. RAG 查询示例
print("\n🔍 步骤3: 知识库查询")
questions = [
    "这些文档主要讲了什么？",
    "总结一下核心观点",
]
for q in questions:
    print(f"\n❓ 问题: {q}")
    result = engine.query_with_sources(q)
    print(f"💡 回答: {result['answer'][:200]}...")
    if result['sources']:
        print(f"📎 来源: {result['sources'][0]['file']}")

# 5. Agent 示例（需要 Ollama 服务运行）
print("\n🤖 步骤4: Agent 任务（需要 Ollama 运行）")
print("   尝试运行: /agent 搜索当前目录的 Python 文件并列出")

try:
    react = ReActEngine()
    answer = react.chat("列出当前目录下的所有 Python 文件")
    print(f"💡 Agent 回答: {answer}")
except Exception as e:
    print(f"   Agent 需要 Ollama 服务运行: {e}")

print("\n✅ 示例完成！")
print("   交互模式: python query_interface.py --data ./data")
print("   Agent 模式: python query_interface.py")
