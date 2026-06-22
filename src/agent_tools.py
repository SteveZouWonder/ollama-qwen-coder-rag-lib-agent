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

def analyze_project_structure(project_path: str = ".") -> str:
    """分析项目结构，提供项目概览"""
    if not os.path.exists(project_path):
        return "[错误] 项目路径不存在: " + project_path
    if not os.path.isdir(project_path):
        return "[错误] 提供的路径不是目录: " + project_path
    
    try:
        analysis = {
            "project_path": os.path.abspath(project_path),
            "structure": {},
            "key_files": [],
            "tech_stack": []
        }
        
        # 列出根目录内容
        items = os.listdir(project_path)
        dirs = [item for item in items if os.path.isdir(os.path.join(project_path, item)) and not item.startswith(".")]
        files = [item for item in items if os.path.isfile(os.path.join(project_path, item)) and not item.startswith(".")]
        
        analysis["structure"]["root_directories"] = dirs
        analysis["structure"]["root_files"] = files
        
        # 识别关键文件
        key_files = []
        tech_indicators = {
            "package.json": "JavaScript/Node.js",
            "requirements.txt": "Python",
            "setup.py": "Python",
            "pyproject.toml": "Python",
            "Cargo.toml": "Rust",
            "go.mod": "Go",
            "pom.xml": "Java/Maven",
            "build.gradle": "Java/Gradle",
            "Gemfile": "Ruby",
            "composer.json": "PHP",
            "README.md": "Documentation",
            "README.rst": "Documentation",
            "Dockerfile": "Docker",
            "docker-compose.yml": "Docker",
            "Makefile": "Make",
            "CMakeLists.txt": "CMake",
        }
        
        for file in files:
            if file in tech_indicators:
                key_files.append(file)
                if tech_indicators[file] not in analysis["tech_stack"]:
                    analysis["tech_stack"].append(tech_indicators[file])
        
        analysis["key_files"] = key_files
        
        # 分析主要目录
        dir_analysis = {}
        for dir_name in dirs[:10]:  # 限制分析前10个目录
            dir_path = os.path.join(project_path, dir_name)
            try:
                sub_items = os.listdir(dir_path)
                sub_files = [item for item in sub_items if os.path.isfile(os.path.join(dir_path, item))]
                sub_dirs = [item for item in sub_items if os.path.isdir(os.path.join(dir_path, item))]
                dir_analysis[dir_name] = {
                    "files_count": len(sub_files),
                    "dirs_count": len(sub_dirs),
                    "sample_files": sub_files[:5]
                }
            except PermissionError:
                dir_analysis[dir_name] = {"error": "权限不足"}
        
        analysis["structure"]["directory_details"] = dir_analysis
        
        # 格式化输出
        lines = ["=== 项目结构分析 ==="]
        lines.append(f"项目路径: {analysis['project_path']}")
        lines.append(f"根目录数: {len(dirs)}")
        lines.append(f"根文件数: {len(files)}")
        lines.append(f"\n主要目录: {', '.join(dirs)}")
        lines.append(f"主要文件: {', '.join(files)}")
        lines.append(f"\n识别的技术栈: {', '.join(analysis['tech_stack']) if analysis['tech_stack'] else '未知'}")
        lines.append(f"\n关键文件: {', '.join(key_files) if key_files else '无'}")
        lines.append(f"\n目录详情:")
        for dir_name, details in dir_analysis.items():
            if "error" not in details:
                lines.append(f"  {dir_name}/: {details['files_count']} 文件, {details['dirs_count']} 子目录")
            else:
                lines.append(f"  {dir_name}/: {details['error']}")
        
        return "\n".join(lines)
    except Exception as e:
        return "[错误] 分析项目结构失败: " + str(e)

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


def read_system_prompt():
    """读取系统提示文件（.devin/SYSTEM_PROMPT.md）"""
    try:
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        if os.path.exists(prompt_file):
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            return f"=== 系统提示内容 ===\n\n{content}\n\n=== 文件路径 ===\n{prompt_file}"
        else:
            return "[提示] 系统提示文件不存在，将使用内置默认提示"
    except Exception as e:
        return f"[错误] 读取系统提示文件失败: {str(e)}"


# ========== 网络搜索工具 ==========

def web_search(query: str, source: str = 'default', max_results: int = 10, use_cache: bool = True, enable_fallback: bool = True) -> str:
    """网络搜索工具 - 支持 DuckDuckGo 搜索，自动降级到Wikipedia"""
    try:
        import asyncio
        from web_search import get_search_engine_manager, get_search_cache, get_result_processor
        
        # 检查缓存
        cache_key = f"{query}_{source}"
        if use_cache:
            cache = get_search_cache()
            cached_results = cache.get(cache_key, source)
            if cached_results:
                processor = get_result_processor()
                return processor.format_results(cached_results, format='text')
        
        # 执行搜索
        manager = get_search_engine_manager()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            if enable_fallback and source == 'default':
                # 使用自动降级功能
                results = loop.run_until_complete(
                    manager.search_with_fallback(query, primary_source='default', 
                                                fallback_sources=['wikipedia'], 
                                                max_results=max_results)
                )
            else:
                # 使用指定搜索引擎
                results = loop.run_until_complete(
                    manager.search(query, source=source, max_results=max_results)
                )
        finally:
            loop.close()
        
        if not results:
            return "[提示] 搜索未返回结果，可能网络不可用或查询无匹配"
        
        # 处理结果
        processor = get_result_processor()
        processed_results = processor.deduplicate(results)
        processed_results = processor.sort_by_relevance(processed_results)
        
        # 缓存结果
        if use_cache:
            cache.set(cache_key, source, processed_results)
        
        return processor.format_results(processed_results, format='text')
        
    except ImportError as e:
        return f"[错误] 网络搜索模块未安装: {e}"
    except Exception as e:
        return f"[错误] 网络搜索失败: {str(e)}"


def web_content_extract(url: str, timeout: int = 30) -> str:
    """提取网页内容并清理格式"""
    try:
        import asyncio
        from web_search import get_content_extractor
        
        extractor = get_content_extractor()
        
        # 验证 URL
        if not extractor.is_valid_url(url):
            return "[错误] 无效的 URL 格式"
        
        # 提取内容
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                extractor.extract(url, timeout=timeout)
            )
        finally:
            loop.close()
        
        if result.get('error'):
            return f"[错误] 内容提取失败: {result['error']}"
        
        # 格式化输出
        output = []
        output.append(f"=== 网页内容提取 ===")
        output.append(f"URL: {result['url']}")
        output.append(f"标题: {result['title']}")
        output.append(f"提取方法: {result['method_used']}")
        
        if result.get('metadata'):
            output.append(f"元数据: {result['metadata']}")
        
        output.append(f"\n=== 正文内容 ===")
        output.append(result['content'][:5000])  # 限制长度
        
        if len(result['content']) > 5000:
            output.append(f"\n... (内容已截断，完整长度: {len(result['content'])} 字符)")
        
        return "\n".join(output)
        
    except ImportError as e:
        return f"[错误] 内容提取模块未安装: {e}"
    except Exception as e:
        return f"[错误] 内容提取失败: {str(e)}"


def web_cache_status() -> str:
    """查看搜索缓存状态"""
    try:
        from web_search import get_search_cache
        
        cache = get_search_cache()
        stats = cache.get_stats()
        size_bytes = cache.get_size()
        size_mb = size_bytes / (1024 * 1024)
        
        output = []
        output.append("=== 搜索缓存状态 ===")
        output.append(f"缓存目录: {stats['cache_dir']}")
        output.append(f"总条目数: {stats['total_entries']}")
        output.append(f"有效条目: {stats['valid_entries']}")
        output.append(f"过期条目: {stats['expired_entries']}")
        output.append(f"最大容量: {stats['max_cache_size']}")
        output.append(f"占用空间: {size_mb:.2f} MB")
        
        if stats['source_distribution']:
            output.append("\n来源分布:")
            for source, count in stats['source_distribution'].items():
                output.append(f"  - {source}: {count} 条")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"[错误] 获取缓存状态失败: {str(e)}"


def web_cache_clear() -> str:
    """清空搜索缓存"""
    try:
        from web_search import get_search_cache
        
        cache = get_search_cache()
        cache.clear()
        
        return "[成功] 搜索缓存已清空"
        
    except Exception as e:
        return f"[错误] 清空缓存失败: {str(e)}"

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
registry.register("analyze_project_structure", analyze_project_structure, "分析项目结构，识别技术栈和关键文件",
                  {"project_path": "项目路径，默认当前目录"}, safe=True)
registry.register("search_files", search_files, "在项目中搜索包含关键字的代码文件",
                  {"query": "搜索关键字(必填)", "path": "搜索目录，默认当前目录", "max_results": "最大结果数，默认10"}, safe=True)
registry.register("get_current_dir", get_current_dir, "获取当前工作目录路径", {}, safe=True)
registry.register("read_system_prompt", read_system_prompt, "读取系统提示文件（必须优先阅读）", {}, safe=True)

# RAG 工具
registry.register("query_knowledge_base", query_knowledge_base, "查询个人知识库（PDF、论文、笔记、OCR识别的图片等文档）",
                  {"question": "查询问题(必填)"}, safe=True)
registry.register("add_to_knowledge_base", add_to_knowledge_base, "将文档添加到知识库（支持PDF/图片/MD/TXT等，自动进行OCR识别）",
                  {"file_path": "文件路径(必填)"}, safe=False)
registry.register("get_knowledge_stats", get_knowledge_stats, "获取知识库统计信息", {}, safe=True)
registry.register("check_knowledge_status", check_knowledge_status, "检查知识库状态（持久化、数据量、OCR功能）", {}, safe=True)

# 网络搜索工具
registry.register("web_search", web_search, "网络搜索（支持 DuckDuckGo + Wikipedia 自动降级）",
                  {"query": "搜索查询(必填)", "source": "搜索来源，默认default", "max_results": "最大结果数，默认10", "use_cache": "是否使用缓存，默认true", "enable_fallback": "是否启用自动降级到Wikipedia，默认true"}, safe=True)
registry.register("web_content_extract", web_content_extract, "提取网页内容并清理格式",
                  {"url": "网页URL(必填)", "timeout": "超时秒数，默认30"}, safe=True)
registry.register("web_cache_status", web_cache_status, "查看搜索缓存状态", {}, safe=True)
registry.register("web_cache_clear", web_cache_clear, "清空搜索缓存", {}, safe=False)

# 代码分析工具
def ast_search(pattern: str, path: str = ".", search_by: str = "name") -> str:
    """AST 语法树搜索（函数、类、变量）"""
    try:
        from code_analyzer import get_ast_analyzer
        
        analyzer = get_ast_analyzer()
        
        results = []
        # 如果是文件，搜索单个文件
        if os.path.isfile(path):
            # 搜索函数
            functions = analyzer.search_functions(path, pattern, search_by)
            results.extend([f"函数: {f.name} (行 {f.line_no}) - {f.parameters}" for f in functions])
            
            # 搜索类
            classes = analyzer.search_classes(path, pattern, search_by)
            results.extend([f"类: {c.name} (行 {c.line_no}) - 基类: {c.bases}" for c in classes])
        
        # 如果是目录，搜索整个项目
        elif os.path.isdir(path):
            project_analysis = analyzer.analyze_project(path, "*.py")
            for file_analysis in project_analysis.get('files', []):
                file_path = file_analysis['file_path']
                for func in file_analysis.get('functions', []):
                    if pattern in func['name']:
                        results.append(f"{file_path}: 函数 {func['name']} (行 {func['line_no']})")
                for cls in file_analysis.get('classes', []):
                    if pattern in cls['name']:
                        results.append(f"{file_path}: 类 {cls['name']} (行 {cls['line_no']})")
        
        if results:
            return f"找到 {len(results)} 个结果:\n" + "\n".join(results[:20])
        else:
            return f"未找到匹配 '{pattern}' 的代码"
        
    except ImportError as e:
        return f"[错误] 代码分析模块未安装: {e}"
    except Exception as e:
        return f"[错误] AST 搜索失败: {str(e)}"


def code_quality_check(path: str = ".", check_type: str = "basic") -> str:
    """代码质量分析（安全、性能、复杂度）"""
    try:
        from code_analyzer import get_quality_checker
        
        checker = get_quality_checker()
        
        if os.path.isfile(path):
            # 检查单个文件
            report = checker.check_file(path, check_types=['basic', check_type])
            return report.summary + "\n\n" + "\n".join([f"{i.line_no}: [{i.severity.value}] {i.message}" for i in report.issues[:10]])
        
        elif os.path.isdir(path):
            # 检查整个项目
            reports = checker.check_project(path)
            summary = checker.get_project_summary(reports)
            
            output = []
            output.append(f"项目质量检查摘要:")
            output.append(f"总文件数: {summary.get('total_files', 0)}")
            output.append(f"总问题数: {summary.get('total_issues', 0)}")
            output.append(f"平均分数: {summary.get('average_score', 0):.1f}/100")
            output.append(f"有问题的文件: {summary.get('files_with_issues', 0)}")
            output.append(f"\n严重程度分布:")
            for severity, count in summary.get('severity_breakdown', {}).items():
                output.append(f"  - {severity}: {count}")
            
            return "\n".join(output)
        
        else:
            return "[错误] 路径不存在"
        
    except ImportError as e:
        return f"[错误] 代码分析模块未安装: {e}"
    except Exception as e:
        return f"[错误] 代码质量检查失败: {str(e)}"


registry.register("ast_search", ast_search, "AST 语法树搜索（函数、类、变量）",
                  {"pattern": "搜索模式(必填)", "path": "搜索路径，默认当前目录", "search_by": "搜索类型（name/parameter/return/base/method），默认name"}, safe=True)
registry.register("code_quality_check", code_quality_check, "代码质量分析（安全、性能、复杂度）",
                  {"path": "代码路径，默认当前目录", "check_type": "检查类型（basic/security/complexity/pylint），默认basic"}, safe=True)

# Git 工具
def git_analyze(repo_path: str = ".", analysis_type: str = "history") -> str:
    """Git 历史分析和变更追踪"""
    try:
        from git_integration import get_git_analyzer
        
        analyzer = get_git_analyzer(repo_path)
        
        if analysis_type == "history":
            commits = analyzer.get_commit_history(max_count=10)
            if not commits:
                return "没有提交历史"
            
            output = []
            output.append(f"最近 {len(commits)} 次提交:")
            for commit in commits:
                output.append(f"\n{commit.commit_hash[:8]} - {commit.author}")
                output.append(f"  {commit.message}")
                output.append(f"  变更文件: {len(commit.changes)}")
                output.append(f"  时间: {commit.date[:19]}")
            
            return "\n".join(output)
        
        elif analysis_type == "status":
            status = analyzer.get_status()
            
            output = []
            output.append(f"当前分支: {status['branch']}")
            output.append(f"暂存文件: {len(status['staged'])}")
            output.append(f"未暂存文件: {len(status['unstaged'])}")
            output.append(f"未跟踪文件: {len(status['untracked'])}")
            
            if status['diverged']:
                output.append(f"分支状态: 领先 {status['ahead']} | 落后 {status['behind']}")
            
            return "\n".join(output)
        
        elif analysis_type == "authors":
            stats = analyzer.get_author_stats()
            
            output = []
            output.append("作者统计:")
            for author, data in list(stats.items())[:10]:
                output.append(f"  {author}: {data['commits']} 次提交")
            
            return "\n".join(output)
        
        else:
            return "[错误] 未知的分析类型，支持: history, status, authors"
        
    except ImportError as e:
        return f"[错误] Git 集成模块未安装: {e}"
    except Exception as e:
        return f"[错误] Git 分析失败: {str(e)}"


def git_commit_gen(repo_path: str = ".", use_ai: bool = True) -> str:
    """生成提交信息"""
    try:
        from git_integration import get_commit_generator
        
        generator = get_commit_generator(repo_path)
        suggestion = generator.generate_commit_message(use_ai=use_ai)
        
        output = []
        output.append("建议的提交信息:")
        output.append(f"标题: {suggestion.title}")
        if suggestion.body:
            output.append(f"\n正文:\n{suggestion.body}")
        if suggestion.conventional_type:
            output.append(f"\n类型: {suggestion.conventional_type}")
        
        return "\n".join(output)
        
    except ImportError as e:
        return f"[错误] Git 集成模块未安装: {e}"
    except Exception as e:
        return f"[错误] 生成提交信息失败: {str(e)}"


registry.register("git_analyze", git_analyze, "Git 历史分析和变更追踪",
                  {"repo_path": "仓库路径，默认当前目录", "analysis_type": "分析类型（history/status/authors），默认history"}, safe=True)
registry.register("git_commit_gen", git_commit_gen, "生成提交信息",
                  {"repo_path": "仓库路径，默认当前目录", "use_ai": "是否使用AI生成，默认true"}, safe=True)

# 知识图谱工具
def knowledge_graph_query(query: str, query_type: str = "entity") -> str:
    """知识图谱查询和推理"""
    try:
        from knowledge_graph import get_graph_query
        
        query_engine = get_graph_query()
        
        if query_type == "entity":
            result = query_engine.query_entity(query)
        elif query_type == "neighbors":
            result = query_engine.query_neighbors(query)
        elif query_type == "path":
            # 路径查询需要两个实体，这里简化处理
            parts = query.split('->')
            if len(parts) == 2:
                result = query_engine.query_path(parts[0].strip(), parts[1].strip())
            else:
                result = query_engine.query_path(query, query)  # 尝试作为单一查询
        elif query_type == "similar":
            result = query_engine.query_similar(query)
        else:
            result = query_engine.query_entity(query)
        
        # 格式化结果
        output = []
        output.append(result.explanation)
        
        if result.entities:
            output.append(f"\n实体 ({len(result.entities)}):")
            for entity in result.entities[:10]:
                output.append(f"  - {entity.text} ({entity.entity_type.value})")
        
        if result.relations:
            output.append(f"\n关系 ({len(result.relations)}):")
            for relation in result.relations[:10]:
                output.append(f"  - {relation.source.text} -> {relation.target.text} ({relation.relation_type.value})")
        
        output.append(f"\n置信度: {result.confidence:.2f}")
        
        return "\n".join(output)
        
    except ImportError as e:
        return f"[错误] 知识图谱模块未安装: {e}"
    except Exception as e:
        return f"[错误] 知识图谱查询失败: {str(e)}"


def knowledge_graph_build(text: str, doc_id: str = "manual", doc_type: str = "text") -> str:
    """构建知识图谱"""
    try:
        from knowledge_graph import get_graph_builder
        
        builder = get_graph_builder()
        
        success = builder.add_document(text, doc_id, doc_type)
        
        if success:
            stats = builder.get_statistics()
            output = []
            output.append("知识图谱构建成功")
            output.append(f"节点数: {stats.total_nodes}")
            output.append(f"边数: {stats.total_edges}")
            output.append(f"实体类型: {list(stats.entity_types.keys())}")
            output.append(f"关系类型: {list(stats.relation_types.keys())}")
            return "\n".join(output)
        else:
            return "[错误] 知识图谱构建失败"
        
    except ImportError as e:
        return f"[错误] 知识图谱模块未安装: {e}"
    except Exception as e:
        return f"[错误] 知识图谱构建失败: {str(e)}"


registry.register("knowledge_graph_query", knowledge_graph_query, "知识图谱查询和推理",
                  {"query": "图谱查询", "query_type": "查询类型（entity/neighbors/path/similar），默认entity"}, safe=True)
registry.register("knowledge_graph_build", knowledge_graph_build, "构建知识图谱",
                  {"text": "文本内容(必填)", "doc_id": "文档ID，默认manual", "doc_type": "文档类型（text/code），默认text"}, safe=True)

# ========== 数据库工具 ==========

def database_connect(db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    连接数据库
    
    Args:
        db_type: 数据库类型（sqlite/mysql/postgresql/mssql）
        database: 数据库路径或名称
        **kwargs: 其他连接参数
        
    Returns:
        连接结果信息
    """
    try:
        from database_tools import DatabaseConnector, DatabaseType
        
        db_type_enum = DatabaseType(db_type.lower())
        connector = DatabaseConnector(db_type_enum, database=database, **kwargs)
        
        if connector.test_connection():
            conn_info = connector.get_connection_info()
            return f"[成功] 数据库连接成功\n类型: {conn_info['db_type']}\n参数: {json.dumps(conn_info['connection_params'], ensure_ascii=False)}"
        else:
            return "[错误] 数据库连接测试失败"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 数据库连接失败: {str(e)}"

def database_query(sql: str, db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    执行SQL查询（SELECT）
    
    Args:
        sql: SQL查询语句
        db_type: 数据库类型
        database: 数据库路径或名称
        **kwargs: 其他连接参数
        
    Returns:
        查询结果
    """
    try:
        from database_tools import DatabaseConnector, DatabaseType, QueryExecutor
        
        db_type_enum = DatabaseType(db_type.lower())
        connector = DatabaseConnector(db_type_enum, database=database, **kwargs)
        executor = QueryExecutor(connector)
        
        result = executor.execute_query(sql)
        
        if result.success:
            output = [f"[成功] 查询执行成功，返回 {result.row_count} 行"]
            output.append(f"执行时间: {result.execution_time:.3f}s")
            output.append("列: " + ", ".join(result.columns))
            
            for row in result.rows:
                output.append(str(row))
            
            return "\n".join(output)
        else:
            return f"[错误] 查询失败: {result.error_message}"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 查询执行失败: {str(e)}"

def database_execute(sql: str, db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    执行SQL语句（INSERT/UPDATE/DELETE）
    
    Args:
        sql: SQL语句
        db_type: 数据库类型
        database: 数据库路径或名称
        **kwargs: 其他连接参数
        
    Returns:
        执行结果
    """
    try:
        from database_tools import DatabaseConnector, DatabaseType, QueryExecutor
        
        db_type_enum = DatabaseType(db_type.lower())
        connector = DatabaseConnector(db_type_enum, database=database, **kwargs)
        executor = QueryExecutor(connector)
        
        result = executor.execute_update(sql)
        
        if result.success:
            return f"[成功] 语句执行成功，影响 {result.affected_rows} 行\n执行时间: {result.execution_time:.3f}s"
        else:
            return f"[错误] 执行失败: {result.error_message}"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 执行失败: {str(e)}"

def database_create_table(table: str, columns: dict, db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    创建数据库表
    
    Args:
        table: 表名
        columns: 列定义字典，如 {"id": "INTEGER PRIMARY KEY", "name": "TEXT"}
        db_type: 数据库类型
        database: 数据库路径或名称
        **kwargs: 其他连接参数
        
    Returns:
        执行结果
    """
    try:
        from database_tools import DatabaseConnector, DatabaseType, QueryExecutor, SQLGenerator
        
        db_type_enum = DatabaseType(db_type.lower())
        connector = DatabaseConnector(db_type_enum, database=database, **kwargs)
        executor = QueryExecutor(connector)
        generator = SQLGenerator()
        
        sql = generator.generate_create_table(table, columns)
        result = executor.execute_update(sql)
        
        if result.success:
            return f"[成功] 表 {table} 创建成功"
        else:
            return f"[错误] 创建表失败: {result.error_message}"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 创建表失败: {str(e)}"

def database_insert(table: str, data: dict, db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    插入数据到表
    
    Args:
        table: 表名
        data: 数据字典，如 {"name": "John", "age": 30}
        db_type: 数据库类型
        database: 数据库路径或名称
        **kwargs: 其他连接参数
        
    Returns:
        执行结果
    """
    try:
        from database_tools import DatabaseConnector, DatabaseType, QueryExecutor, SQLGenerator
        
        db_type_enum = DatabaseType(db_type.lower())
        connector = DatabaseConnector(db_type_enum, database=database, **kwargs)
        executor = QueryExecutor(connector)
        generator = SQLGenerator()
        
        sql, params = generator.generate_insert(table, data)
        result = executor.execute_update(sql, params)
        
        if result.success:
            return f"[成功] 数据插入成功，影响 {result.affected_rows} 行"
        else:
            return f"[错误] 插入数据失败: {result.error_message}"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 插入数据失败: {str(e)}"

def database_get_schema(table: str, db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    获取表结构
    
    Args:
        table: 表名
        db_type: 数据库类型
        database: 数据库路径或名称
        **kwargs: 其他连接参数
        
    Returns:
        表结构信息
    """
    try:
        from database_tools import DatabaseConnector, DatabaseType, QueryExecutor
        
        db_type_enum = DatabaseType(db_type.lower())
        connector = DatabaseConnector(db_type_enum, database=database, **kwargs)
        executor = QueryExecutor(connector)
        
        schema = executor.get_table_schema(table)
        
        if schema:
            output = [f"[表] {schema['table_name']}"]
            output.append("[列信息]")
            for col in schema['columns']:
                output.append(f"  {col['name']}: {col['type']} (NOT NULL: {col['not_null']}, PK: {col['primary_key']})")
            return "\n".join(output)
        else:
            return "[错误] 获取表结构失败"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 获取表结构失败: {str(e)}"

# 注册数据库工具
registry.register("database_connect", database_connect, "连接数据库",
                  {"db_type": "数据库类型（sqlite/mysql/postgresql/mssql），默认sqlite", "database": "数据库路径或名称，默认:memory:"}, safe=True)
registry.register("database_query", database_query, "执行SQL查询（SELECT）",
                  {"sql": "SQL查询语句(必填)", "db_type": "数据库类型，默认sqlite", "database": "数据库路径或名称，默认:memory:"}, safe=True)
registry.register("database_execute", database_execute, "执行SQL语句（INSERT/UPDATE/DELETE）",
                  {"sql": "SQL语句(必填)", "db_type": "数据库类型，默认sqlite", "database": "数据库路径或名称，默认:memory:"}, safe=False)
registry.register("database_create_table", database_create_table, "创建数据库表",
                  {"table": "表名(必填)", "columns": "列定义字典(必填)，如 {\"id\": \"INTEGER PRIMARY KEY\", \"name\": \"TEXT\"}", "db_type": "数据库类型，默认sqlite", "database": "数据库路径或名称，默认:memory:"}, safe=False)
registry.register("database_insert", database_insert, "插入数据到表",
                  {"table": "表名(必填)", "data": "数据字典(必填)，如 {\"name\": \"John\", \"age\": 30}", "db_type": "数据库类型，默认sqlite", "database": "数据库路径或名称，默认:memory:"}, safe=False)
registry.register("database_get_schema", database_get_schema, "获取表结构",
                  {"table": "表名(必填)", "db_type": "数据库类型，默认sqlite", "database": "数据库路径或名称，默认:memory:"}, safe=True)
