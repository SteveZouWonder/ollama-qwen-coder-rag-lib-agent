#!/usr/bin/env python3
"""
Agent 工具链实现 - 带安全确认 + RAG 知识库集成
"""
import os
import subprocess
import json
import re
from typing import Dict, Any, Callable, List

# ========== RAG 引擎引用（由外部注入）==========
_rag_engine = None

def set_rag_engine(engine):
    """注入 RAG 引擎实例，供知识库工具使用"""
    global _rag_engine
    _rag_engine = engine

# ========== 工具注册中心 ==========

class ToolRegistry:
    """工具注册中心"""
    def __init__(self):
        self.tools: Dict[str, Dict] = {}

    def register(self, name: str, func: Callable, description: str, params: Dict[str, str], safe: bool = True):
        self.tools[name] = {
            "function": func,
            "description": description,
            "parameters": params,
            "safe": safe
        }

    def get_descriptions(self) -> str:
        lines = ["=== 可用工具 ==="]
        for name, info in self.tools.items():
            safe_tag = "[安全]" if info["safe"] else "[需确认]"
            lines.append("")
            lines.append(safe_tag + " 工具名: " + name)
            lines.append("    描述: " + info['description'])
            param_lines = []
            for k, v in info["parameters"].items():
                param_lines.append("      - " + k + ": " + v)
            if param_lines:
                lines.append("    参数:")
                lines.extend(param_lines)
            else:
                lines.append("    参数: 无")
            if info['parameters']:
                first_key = list(info['parameters'].keys())[0]
                example = '    调用格式: Action: ' + name + '\n    Action Input: {"' + first_key + '": "值"}'
            else:
                example = '    调用格式: Action: ' + name + '\n    Action Input: {}'
            lines.append(example)
        return "\n".join(lines)

    def execute(self, name: str, args: Dict, auto_confirm: bool = False) -> str:
        if name not in self.tools:
            return "[错误] 未知工具: " + name
        tool = self.tools[name]
        try:
            if not tool["safe"] and not auto_confirm:
                return "[CONFIRM_REQUIRED] " + name + "|" + json.dumps(args, ensure_ascii=False)
            result = tool["function"](**args)
            return str(result)[:5000]
        except Exception as e:
            return "[错误] 工具执行失败: " + str(e)

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())

# ========== 命令安全分析 ==========

class CommandSafetyChecker:
    """命令安全分析器"""

    DANGEROUS_PATTERNS = [
        r"rm\s+-rf\s+/", r"rm\s+-rf\s+/\*", r"dd\s+if=/dev/zero",
        r"mkfs\.", r">\s*/dev/sda", r"chmod\s+777\s+/",
        r"curl\s+.*\|\s*sh", r"wget\s+.*\|\s*sh", r"sudo\s+rm",
        r"del\s+/f\s+/s\s+/q", r"format\s+", r":\(\)\{\s*:\|:&\s*\};:",
        r"mv\s+/\s+", r"cp\s+/\s+", r"ln\s+-sf\s+/",
    ]

    READONLY_PATTERNS = [
        r"^ls\b", r"^pwd\b", r"^echo\b", r"^cat\b", r"^head\b",
        r"^tail\b", r"^find\b", r"^grep\b", r"^wc\b", r"^ps\b",
        r"^which\b", r"^whereis\b", r"^uname\b", r"^whoami\b",
        r"^date\b", r"^df\b", r"^du\b", r"^top\b", r"^htop\b",
        r"^git\s+status\b", r"^git\s+log\b", r"^git\s+diff\b",
        r"^git\s+branch\b", r"^git\s+remote\b", r"^git\s+show\b",
        r"^python\s+-m\s+pytest\s+--collect-only\b",
        r"^pip\s+list\b", r"^pip\s+freeze\b",
        r"^ollama\s+list\b", r"^ollama\s+ps\b",
        r"^tree\b", r"^file\b", r"^stat\b",
    ]

    @classmethod
    def analyze(cls, command: str) -> Dict[str, Any]:
        result = {
            "command": command,
            "is_dangerous": False,
            "danger_reasons": [],
            "is_readonly": False,
            "needs_confirm": True,
            "risk_level": "unknown",
        }

        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                result["is_dangerous"] = True
                result["danger_reasons"].append("匹配危险模式: " + pattern)

        for pattern in cls.READONLY_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                result["is_readonly"] = True
                break

        if result["is_dangerous"]:
            result["risk_level"] = "critical"
            result["needs_confirm"] = True
        elif result["is_readonly"]:
            result["risk_level"] = "low"
            result["needs_confirm"] = False
        elif any(kw in command.lower() for kw in ["rm", "del", "drop", "truncate", "format"]):
            result["risk_level"] = "high"
            result["needs_confirm"] = True
        elif any(kw in command.lower() for kw in ["write", "insert", "update", "delete", "chmod", "chown", "mv", "cp"]):
            result["risk_level"] = "medium"
            result["needs_confirm"] = True
        else:
            result["risk_level"] = "low"
            result["needs_confirm"] = False

        return result

# ========== 具体工具实现 ==========

def read_file(path: str, offset: int = 0, limit: int = 100) -> str:
    if not os.path.exists(path):
        return "[错误] 文件不存在: " + path
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            if not lines:
                return "[文件为空]"
            start = max(0, offset)
            end = min(start + limit, len(lines))
            selected = lines[start:end]
            result = "".join(selected)
            info = "[文件: " + path + " | 总行数: " + str(len(lines)) + " | 显示: " + str(start+1) + "-" + str(end) + "]\n"
            if end < len(lines):
                result = result + "\n... (" + str(len(lines) - end) + " 行省略) ..."
            return info + result
    except Exception as e:
        return "[错误] 读取失败: " + str(e)

def write_file(path: str, content: str, append: bool = False) -> str:
    try:
        abs_path = os.path.abspath(path)
        parent = os.path.dirname(abs_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        mode = "a" if append else "w"
        with open(abs_path, mode, encoding="utf-8") as f:
            f.write(content)
        action = "追加" if append else "写入"
        return "[成功] " + action + " " + abs_path + "，共 " + str(len(content)) + " 字符"
    except Exception as e:
        return "[错误] 写入失败: " + str(e)

def execute_command(command: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd()
        )
        output = []
        if result.stdout:
            output.append(result.stdout)
        if result.stderr:
            output.append("[stderr] " + result.stderr)
        if result.returncode != 0:
            output.append("[退出码] " + str(result.returncode))
        return "\n".join(output)[:4000]
    except subprocess.TimeoutExpired:
        return "[错误] 命令超时 (> " + str(timeout) + "s): " + command
    except Exception as e:
        return "[错误] 执行失败: " + str(e)

def list_directory(path: str = ".") -> str:
    if not os.path.exists(path):
        return "[错误] 目录不存在: " + path
    try:
        items = os.listdir(path)
        lines = ["[目录] " + os.path.abspath(path)]
        dirs = []
        files = []
        for item in sorted(items):
            if item.startswith("."):
                continue
            full = os.path.join(path, item)
            if os.path.isdir(full):
                dirs.append("  [D] " + item + "/")
            else:
                files.append("  [F] " + item)
        lines.extend(dirs)
        lines.extend(files)
        return "\n".join(lines)
    except Exception as e:
        return "[错误] " + str(e)

def search_files(query: str, path: str = ".", max_results: int = 10) -> str:
    results = []
    exts = {".py", ".js", ".java", ".ts", ".go", ".rs", ".c", ".cpp", ".h", ".md", ".txt", ".json", ".yaml", ".yml", ".sql", ".sh"}
    skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".idea", ".vscode"}

    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for file in files:
                if any(file.endswith(ext) for ext in exts):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            if query in content:
                                lines = content.split("\n")
                                matches = []
                                for i, line in enumerate(lines):
                                    if query in line:
                                        matches.append("    行" + str(i+1) + ": " + line.strip())
                                    if len(matches) >= 3:
                                        break
                                results.append("[匹配] " + filepath + "\n" + "\n".join(matches))
                                if len(results) >= max_results:
                                    break
                    except:
                        continue
                if len(results) >= max_results:
                    break
        if not results:
            return "[结果] 未找到包含 '" + query + "' 的文件"
        return "\n\n".join(results)
    except Exception as e:
        return "[错误] " + str(e)

def get_current_dir() -> str:
    return os.getcwd()

# ========== RAG 知识库工具 ==========

def query_knowledge_base(question: str) -> str:
    """查询个人知识库（PDF、论文、笔记等）"""
    global _rag_engine
    if _rag_engine is None:
        return "[错误] 知识库引擎未初始化"
    try:
        return _rag_engine.query_tool(question)
    except Exception as e:
        return "[错误] 知识库查询失败: " + str(e)

def add_to_knowledge_base(file_path: str) -> str:
    """将文档添加到知识库"""
    global _rag_engine
    if _rag_engine is None:
        return "[错误] 知识库引擎未初始化"
    try:
        return _rag_engine.add_document_tool(file_path)
    except Exception as e:
        return "[错误] 添加文档失败: " + str(e)

def get_knowledge_stats() -> str:
    """获取知识库统计信息"""
    global _rag_engine
    if _rag_engine is None:
        return "[错误] 知识库引擎未初始化"
    try:
        return _rag_engine.get_stats_tool()
    except Exception as e:
        return "[错误] 获取统计信息失败: " + str(e)

def check_knowledge_status() -> str:
    """检查知识库状态，包括持久化和数据情况"""
    global _rag_engine
    if _rag_engine is None:
        return "[错误] 知识库引擎未初始化"
    try:
        from pathlib import Path
        from config import INDEX_DIR
        
        status_info = []
        status_info.append("=== 知识库状态检查 ===")
        
        # 检查持久化目录
        index_dir = Path(INDEX_DIR)
        if index_dir.exists():
            status_info.append(f"✅ 持久化目录存在: {index_dir}")
            status_info.append(f"   - ChromaDB: {index_dir / 'chroma_db'}")
            status_info.append(f"   - LlamaIndex: {index_dir / 'llama_index'}")
        else:
            status_info.append(f"❌ 持久化目录不存在: {index_dir}")
        
        # 检查数据量
        try:
            doc_count = _rag_engine.chroma_collection.count()
            status_info.append(f"✅ 向量数据库中包含 {doc_count} 个文档块")
        except Exception as e:
            status_info.append(f"⚠️ 无法获取文档数量: {e}")
        
        # 检查索引状态
        if _rag_engine.index is not None:
            status_info.append("✅ 索引已加载到内存")
        else:
            status_info.append("⚠️ 索引未加载到内存（但持久化数据可能存在）")
        
        # 检查 OCR 功能
        try:
            from config import OCR_ENABLED, OCR_ENGINE
            status_info.append(f"✅ OCR 功能: {'启用' if OCR_ENABLED else '禁用'}")
            if OCR_ENABLED:
                status_info.append(f"   - OCR 引擎: {OCR_ENGINE}")
                status_info.append("   - 支持格式: PNG, JPG, JPEG, 扫描版 PDF")
        except ImportError:
            status_info.append("⚠️ OCR 配置不可用")
        
        return "\n".join(status_info)
    except Exception as e:
        return "[错误] 状态检查失败: " + str(e)

# ========== 初始化注册表 ==========
registry = ToolRegistry()
registry.register("read_file", read_file, "读取文件内容，支持指定行范围",
                  {"path": "文件路径(必填)", "offset": "起始行号，默认0", "limit": "最大行数，默认100"}, safe=True)
registry.register("write_file", write_file, "写入或追加内容到文件",
                  {"path": "文件路径(必填)", "content": "文件内容(必填)", "append": "是否追加，默认false"}, safe=False)
registry.register("execute_command", execute_command, "执行shell命令（如python test.py, ls, git status等）",
                  {"command": "命令字符串(必填)", "timeout": "超时秒数，默认30"}, safe=False)
registry.register("list_directory", list_directory, "列出目录内容",
                  {"path": "目录路径，默认当前目录"}, safe=True)
registry.register("search_files", search_files, "在项目中搜索包含关键字的代码文件",
                  {"query": "搜索关键字(必填)", "path": "搜索目录，默认当前目录", "max_results": "最大结果数，默认10"}, safe=True)
registry.register("get_current_dir", get_current_dir, "获取当前工作目录路径", {}, safe=True)

# RAG 工具
registry.register("query_knowledge_base", query_knowledge_base, "查询个人知识库（PDF、论文、笔记、OCR识别的图片等文档）",
                  {"question": "查询问题(必填)"}, safe=True)
registry.register("add_to_knowledge_base", add_to_knowledge_base, "将文档添加到知识库（支持PDF/图片/MD/TXT等，自动进行OCR识别）",
                  {"file_path": "文件路径(必填)"}, safe=False)
registry.register("get_knowledge_stats", get_knowledge_stats, "获取知识库统计信息", {}, safe=True)
registry.register("check_knowledge_status", check_knowledge_status, "检查知识库状态（持久化、数据量、OCR功能）", {}, safe=True)
