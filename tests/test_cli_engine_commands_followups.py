#!/usr/bin/env python3
"""F10 P3-2 拆分时发现的 CLI 缺陷回归（见 docs/features/f10-hardening/README.md「待办」）。

#6 ``/ask`` 内联文件路径只认 ``/Users/``；#2 ``/file`` 在 Rich 终端不记录命令；
#1 可选模块探测把"装了但导入出错"吞成"未安装"；#3 ``handle_natural`` 判空用的引擎与路由用的不一致。
"""
import logging
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import cli.engine_commands as ec
import optional_deps
from cli.handlers import CLIContext
from cli.parser import ParsedCommand


def _ctx(**kw):
    return CLIContext(console=MagicMock(), has_rich=True, **kw)


# ---------- #6 内联文件路径检测跨平台 ----------

class TestDetectInlineFile:
    @pytest.mark.parametrize("prefix", ["/home/u/docs", "/Users/u/docs", "/srv/data", "/tmp/x"])
    def test_posix_absolute_paths(self, tmp_path, prefix, monkeypatch):
        f = tmp_path / "报告.pdf"
        f.write_text("x")
        # 用真实存在的文件替代平台目录（只检查"绝对路径 + 存在"，不再依赖 /Users/ 前缀）
        q = f"请分析 {f} 里的结论"
        assert ec._detect_inline_file(q) == str(f)

    def test_home_tilde_detected_as_written(self, tmp_path, monkeypatch):
        """``~/`` 按展开后的真实文件判存在，但返回问题里的原文（供 ``_ingest_inline_file`` 从问题中剔除）。"""
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "notes.md").write_text("x")
        assert ec._detect_inline_file("看一下 ~/notes.md") == "~/notes.md"
        assert ec._detect_inline_file("看一下 ~/missing.md") is None

    def test_ingest_expands_tilde_for_loader(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "notes.md").write_text("x")
        loaded = {}
        fake_docs = [MagicMock(text="abc")]
        monkeypatch.setattr("document_loader.load_documents", lambda p, *a, **k: loaded.setdefault("p", p) and fake_docs)
        monkeypatch.setattr("cli.state.rag_engine", MagicMock())
        with patch("cli.state.console"), patch("builtins.print"):
            q = ec._ingest_inline_file("~/notes.md", "看一下 ~/notes.md")
        assert loaded["p"] == str(tmp_path / "notes.md")
        assert "~/" not in q and "notes.md" in q

    def test_windows_drive_path(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(ec.os.path, "isfile", lambda p: seen.setdefault("p", p) or True)
        assert ec._detect_inline_file(r"分析 C:\Users\me\scan.PNG 里的表格") == r"C:\Users\me\scan.PNG"
        assert ec._detect_inline_file("分析 D:/data/a.txt") == "D:/data/a.txt"

    def test_extension_whitelist_and_case(self, tmp_path):
        (tmp_path / "a.JPEG").write_text("x")
        (tmp_path / "a.py").write_text("x")
        assert ec._detect_inline_file(f"看 {tmp_path / 'a.JPEG'}") == str(tmp_path / "a.JPEG")
        assert ec._detect_inline_file(f"看 {tmp_path / 'a.py'}") is None

    def test_nonexistent_or_relative_ignored(self, tmp_path):
        assert ec._detect_inline_file(f"看 {tmp_path / 'missing.pdf'}") is None
        assert ec._detect_inline_file("看 docs/readme.md") is None
        assert ec._detect_inline_file("HTTP/3 用什么协议？") is None
        assert ec._detect_inline_file("") is None

    def test_run_ask_ingests_linux_path(self, tmp_path, monkeypatch):
        """端到端：Linux 路径进入 ``_run_ask`` 会触发内联入库（修复前正则只认 /Users/）。"""
        f = tmp_path / "home_user_doc.md"
        f.write_text("hello")
        ingest = MagicMock(return_value="改写后的问题")
        monkeypatch.setattr(ec, "_ingest_inline_file", ingest)
        monkeypatch.setattr(ec, "_health_before", lambda q: {})
        monkeypatch.setattr(ec, "_conversation", lambda: None)
        monkeypatch.setattr(ec, "record_command_execution", lambda *a, **k: None)
        monkeypatch.setattr(ec, "record_conversation", lambda *a, **k: None)
        monkeypatch.setattr(ec.rag_pipeline, "answer_question", lambda *a, **k: {"kind": "meta"})
        monkeypatch.setattr(ec, "_live_answer", lambda *a, **k: MagicMock())
        monkeypatch.setattr("cli.state.rag_engine", MagicMock())
        assert ec._run_ask(_ctx(), f"分析 {f}") is True
        ingest.assert_called_once_with(str(f), f"分析 {f}")


# ---------- #2 /file 在 Rich 终端也要记录命令 ----------

class TestHandleFileRecords:
    @pytest.mark.parametrize("has_rich", [True, False])
    def test_file_recorded_regardless_of_rich(self, has_rich, monkeypatch):
        rec = MagicMock()
        registry = MagicMock()
        registry.execute.return_value = "内容"
        monkeypatch.setattr(ec, "record_command_execution", rec)
        monkeypatch.setattr(ec, "registry", registry)
        with patch("cli.state.HAS_RICH", has_rich), patch("cli.state.console"), patch("builtins.print"):
            assert ec.handle_file(_ctx(), ParsedCommand("file", "/file a.md", "a.md")) is True
        rec.assert_called_once_with("read", "a.md")


# ---------- #1 可选模块探测 ----------

class TestProbeModules:
    def test_missing_target_is_quiet(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="optional_deps"):
            assert optional_deps.probe_modules("definitely_not_a_module_xyz", feature="X") is False
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_broken_target_warns(self, caplog, monkeypatch):
        """目标模块存在，但内部 ``from state.command_recommender import …`` 之类拼错 → 不是"未安装"。"""
        broken = types.ModuleType("broken_opt_mod")
        def _load():
            raise ModuleNotFoundError("No module named 'state'", name="state")
        monkeypatch.setitem(sys.modules, "broken_opt_mod", None)  # 强制走 import 机制
        monkeypatch.setattr(optional_deps.importlib, "import_module",
                            lambda m: _load() if m == "broken_opt_mod" else broken)
        with caplog.at_level(logging.WARNING, logger="optional_deps"):
            assert optional_deps.probe_modules("broken_opt_mod", feature="推荐系统") is False
        assert any("推荐系统" in r.getMessage() and "state" in r.getMessage()
                   for r in caplog.records if r.levelno == logging.WARNING)

    def test_other_exception_warns(self, caplog, monkeypatch):
        def _boom(m):
            raise RuntimeError("init failed")
        monkeypatch.setattr(optional_deps.importlib, "import_module", _boom)
        with caplog.at_level(logging.WARNING, logger="optional_deps"):
            assert optional_deps.probe_modules("whatever", feature="F") is False
        assert any("非缺失" in r.getMessage() for r in caplog.records)

    def test_submodule_missing_counts_as_target_missing(self):
        e = ModuleNotFoundError("x", name="pkg.sub")
        assert optional_deps._is_missing_target(e, "pkg") is True
        assert optional_deps._is_missing_target(ModuleNotFoundError("x", name="other"), "pkg") is False

    def test_real_modules_available(self):
        assert optional_deps.probe_modules("command_recommender", feature="推荐") is True
        assert optional_deps.probe_modules("knowledge_to_skills", "knowledge_snapshot") is True

    def test_entry_flags_use_probe(self):
        import query_interface as qi
        assert qi.RECOMMENDER_AVAILABLE is True
        assert ec.KNOWLEDGE_MANAGEMENT_AVAILABLE is True
        import inspect
        assert "probe_modules" in inspect.getsource(qi)
        assert "probe_modules" in inspect.getsource(ec)


# ---------- #3 handle_natural 判空引擎一致 ----------

class TestHandleNaturalEngine:
    def test_uninitialized_hint_uses_ctx_engine(self, monkeypatch):
        """ctx 注入的引擎 retriever 为 None → 提示"知识库未初始化"，即使全局 state.rag_engine 已就绪。"""
        ctx_engine = MagicMock(retriever=None)
        ready_engine = MagicMock(retriever=object())
        monkeypatch.setattr("cli.state.rag_engine", ready_engine)
        monkeypatch.setattr(ec.Config, "AUTO_ROUTE", False)
        printed = []
        monkeypatch.setattr("cli.state.console", MagicMock(print=lambda *a, **k: printed.append(str(a[0]))))
        monkeypatch.setattr(ec, "_run_ask", lambda ctx, text, cmd_name: True)
        assert ec.handle_natural(_ctx(rag_engine=ctx_engine), ParsedCommand("natural", "你好", "你好")) is True
        assert any("知识库未初始化" in p for p in printed)

    def test_no_hint_when_ctx_engine_ready(self, monkeypatch):
        monkeypatch.setattr("cli.state.rag_engine", MagicMock(retriever=None))
        monkeypatch.setattr(ec.Config, "AUTO_ROUTE", False)
        printed = []
        monkeypatch.setattr("cli.state.console", MagicMock(print=lambda *a, **k: printed.append(str(a[0]))))
        monkeypatch.setattr(ec, "_run_ask", lambda ctx, text, cmd_name: True)
        ec.handle_natural(_ctx(rag_engine=MagicMock(retriever=object())), ParsedCommand("natural", "你好", "你好"))
        assert not any("知识库未初始化" in p for p in printed)
