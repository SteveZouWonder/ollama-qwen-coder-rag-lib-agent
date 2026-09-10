#!/usr/bin/env python3
"""test_tesseract_detection.py — F10 P3-1：Tesseract 跨平台探测与缺失提示。

覆盖：
- ``config.resolve_tesseract_path`` 的四级顺序（TESSERACT_PATH → shutil.which → 平台候选 → None），
  monkeypatch ``shutil.which`` / ``os.path.exists`` / ``sys.platform`` 覆盖 macOS / Linux / Windows 命中与未找到；
- ``config.describe_tesseract`` 的来源 / 提示语义（含 TESSERACT_PATH 指向不存在文件）；
- ``DocumentLoader``：Tesseract 缺失时 OCR 关闭并给出"未检测到 Tesseract + 安装文档"提示，图片 / PDF 跳过时原样转述；
- ``TesseractOCREngine`` 不可用时的异常文案含安装文档；
- CLI ``/config`` 与 Web ``env_info`` / ``format_env_info`` 显示探测结果；``check_knowledge_status`` 工具；
- ``bootstrap.check_tesseract`` 仅提示一次（持久标记 + 进程内标记）并接入 ``ensure_ollama_ready``。

所有用例不依赖本机是否安装 Tesseract：探测函数全部打桩。
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

import config as cfg


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _exists_only(*paths):
    """构造 os.path.exists 替身：仅 ``paths`` 中的路径存在。"""
    allowed = {os.path.normpath(p) for p in paths}
    return lambda p: os.path.normpath(str(p)) in allowed


@pytest.fixture
def no_env(monkeypatch):
    """清掉环境变量与模块常量里的 TESSERACT_PATH，让探测从 PATH 开始。"""
    monkeypatch.delenv("TESSERACT_PATH", raising=False)
    monkeypatch.setattr(cfg, "TESSERACT_PATH", "")


@pytest.fixture
def nothing_found(monkeypatch, no_env):
    """PATH 与所有候选都找不到。"""
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(os.path, "exists", lambda p: False)


# ---------------------------------------------------------------------------
# tesseract_candidates：三平台候选表
# ---------------------------------------------------------------------------
class TestCandidates:
    def test_darwin(self):
        assert cfg.tesseract_candidates("darwin") == ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"]

    def test_linux(self):
        assert cfg.tesseract_candidates("linux") == ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]

    def test_windows_uses_env_roots(self, monkeypatch):
        monkeypatch.setenv("ProgramFiles", r"D:\PF")
        monkeypatch.setenv("ProgramFiles(x86)", r"D:\PF86")
        monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\u\AppData\Local")
        cands = cfg.tesseract_candidates("win32")
        assert cands[0] == os.path.join(r"D:\PF", "Tesseract-OCR", "tesseract.exe")
        assert cands[1] == os.path.join(r"D:\PF86", "Tesseract-OCR", "tesseract.exe")
        assert cands[2] == os.path.join(r"C:\Users\u\AppData\Local", "Programs", "Tesseract-OCR", "tesseract.exe")

    def test_windows_without_localappdata(self, monkeypatch):
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.delenv("ProgramFiles", raising=False)
        monkeypatch.delenv("ProgramFiles(x86)", raising=False)
        cands = cfg.tesseract_candidates("win32")
        assert len(cands) == 2 and all(c.endswith("tesseract.exe") for c in cands)
        assert cands[0].startswith(r"C:\Program Files")

    def test_default_platform_is_sys_platform(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert cfg.tesseract_candidates() == cfg.tesseract_candidates("linux")
        monkeypatch.setattr(sys, "platform", "darwin")
        assert cfg.tesseract_candidates()[0].startswith("/opt/homebrew")

    def test_unknown_platform_falls_back_to_posix(self):
        assert cfg.tesseract_candidates("freebsd13") == ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]


# ---------------------------------------------------------------------------
# resolve_tesseract_path：四级顺序
# ---------------------------------------------------------------------------
class TestResolveOrder:
    def test_env_path_wins_when_exists(self, monkeypatch, no_env):
        monkeypatch.setenv("TESSERACT_PATH", "/custom/tess")
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/tesseract")
        monkeypatch.setattr(os.path, "exists", _exists_only("/custom/tess", "/usr/bin/tesseract"))
        assert cfg.resolve_tesseract_path() == "/custom/tess"

    def test_env_path_expands_user(self, monkeypatch, no_env, tmp_path):
        exe = tmp_path / "tesseract"
        exe.write_text("")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("TESSERACT_PATH", "~/tesseract")
        assert cfg.resolve_tesseract_path() == str(exe)

    def test_env_path_missing_falls_through_to_which(self, monkeypatch, no_env):
        monkeypatch.setenv("TESSERACT_PATH", "/nope/tess")
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/tesseract")
        monkeypatch.setattr(os.path, "exists", _exists_only("/usr/bin/tesseract"))
        assert cfg.resolve_tesseract_path() == "/usr/bin/tesseract"

    def test_module_constant_used_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("TESSERACT_PATH", raising=False)
        monkeypatch.setattr(cfg, "TESSERACT_PATH", "/from/const")
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(os.path, "exists", _exists_only("/from/const"))
        assert cfg.resolve_tesseract_path() == "/from/const"

    def test_explicit_arg_overrides_env(self, monkeypatch, no_env):
        monkeypatch.setenv("TESSERACT_PATH", "/env/tess")
        monkeypatch.setattr(os.path, "exists", _exists_only("/env/tess", "/arg/tess"))
        assert cfg.resolve_tesseract_path(env_path="/arg/tess") == "/arg/tess"

    def test_which_wins_over_candidates(self, monkeypatch, no_env):
        monkeypatch.setattr("shutil.which", lambda name: "/somewhere/on/path/tesseract")
        monkeypatch.setattr(os.path, "exists", lambda p: True)
        assert cfg.resolve_tesseract_path(platform="darwin") == "/somewhere/on/path/tesseract"

    def test_which_called_with_tesseract(self, monkeypatch, no_env):
        seen = []

        def fake_which(name):
            seen.append(name)
            return None

        monkeypatch.setattr("shutil.which", fake_which)
        monkeypatch.setattr(os.path, "exists", lambda p: False)
        cfg.resolve_tesseract_path()
        assert seen == ["tesseract"]


class TestResolvePerPlatform:
    """PATH 里没有时按平台候选命中；三平台各一例 + 未找到。"""

    def test_macos_homebrew(self, monkeypatch, no_env):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(os.path, "exists", _exists_only("/opt/homebrew/bin/tesseract"))
        assert cfg.resolve_tesseract_path() == "/opt/homebrew/bin/tesseract"

    def test_macos_usr_local_when_homebrew_absent(self, monkeypatch, no_env):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(os.path, "exists", _exists_only("/usr/local/bin/tesseract"))
        assert cfg.resolve_tesseract_path() == "/usr/local/bin/tesseract"

    def test_linux_usr_bin(self, monkeypatch, no_env):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(os.path, "exists", _exists_only("/usr/bin/tesseract"))
        assert cfg.resolve_tesseract_path() == "/usr/bin/tesseract"

    def test_linux_does_not_probe_homebrew_path(self, monkeypatch, no_env):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr("shutil.which", lambda name: None)
        # 只有 macOS 路径"存在"——Linux 下不应命中它
        monkeypatch.setattr(os.path, "exists", _exists_only("/opt/homebrew/bin/tesseract"))
        assert cfg.resolve_tesseract_path() is None

    def test_windows_program_files(self, monkeypatch, no_env):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
        monkeypatch.delenv("ProgramFiles(x86)", raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        target = os.path.join(r"C:\Program Files", "Tesseract-OCR", "tesseract.exe")
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(os.path, "exists", _exists_only(target))
        assert cfg.resolve_tesseract_path() == target

    def test_windows_localappdata(self, monkeypatch, no_env):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\u\AppData\Local")
        target = os.path.join(r"C:\Users\u\AppData\Local", "Programs", "Tesseract-OCR", "tesseract.exe")
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(os.path, "exists", _exists_only(target))
        assert cfg.resolve_tesseract_path() == target

    @pytest.mark.parametrize("plat", ["darwin", "linux", "win32"])
    def test_not_found_returns_none(self, monkeypatch, nothing_found, plat):
        monkeypatch.setattr(sys, "platform", plat)
        assert cfg.resolve_tesseract_path() is None

    def test_no_hardcoded_macos_default(self):
        """回归守卫：模块常量不再写死 Homebrew 路径（那正是 Linux / Windows 报路径错误的根源）。"""
        assert cfg.TESSERACT_PATH == (os.environ.get("TESSERACT_PATH") or "")
        assert cfg.Config.TESSERACT_MISSING_HINT == cfg.TESSERACT_MISSING_HINT
        assert "docs/tutorials/02-installation.md#ocr" in cfg.TESSERACT_MISSING_HINT
        assert cfg.Config.TESSERACT_INSTALL_DOC == "docs/tutorials/02-installation.md#ocr"


# ---------------------------------------------------------------------------
# describe_tesseract：来源与提示
# ---------------------------------------------------------------------------
class TestDescribe:
    def test_env_source(self, monkeypatch, no_env):
        monkeypatch.setenv("TESSERACT_PATH", "/custom/tess")
        monkeypatch.setattr(os.path, "exists", _exists_only("/custom/tess"))
        d = cfg.describe_tesseract()
        assert d == {"path": "/custom/tess", "source": "env", "installed": True, "hint": None}

    def test_path_source(self, monkeypatch, no_env):
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/tesseract")
        d = cfg.describe_tesseract()
        assert d["source"] == "path" and d["path"] == "/usr/bin/tesseract" and d["hint"] is None

    def test_candidate_source(self, monkeypatch, no_env):
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(os.path, "exists", _exists_only("/usr/bin/tesseract"))
        d = cfg.describe_tesseract(platform="linux")
        assert d["source"] == "candidate" and d["installed"] is True

    def test_missing(self, nothing_found):
        d = cfg.describe_tesseract()
        assert d["installed"] is False and d["path"] is None and d["source"] is None
        assert d["hint"] == cfg.TESSERACT_MISSING_HINT
        assert "docs/tutorials/02-installation.md#ocr" in d["hint"]

    def test_env_points_to_missing_file_and_nothing_else(self, monkeypatch, nothing_found):
        monkeypatch.setenv("TESSERACT_PATH", "/nope/tess")
        d = cfg.describe_tesseract()
        assert d["installed"] is False
        assert d["hint"].startswith("TESSERACT_PATH=/nope/tess 指向的文件不存在")
        assert cfg.TESSERACT_MISSING_HINT in d["hint"]

    def test_env_points_to_missing_file_but_found_elsewhere(self, monkeypatch, no_env):
        monkeypatch.setenv("TESSERACT_PATH", "/nope/tess")
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/tesseract")
        monkeypatch.setattr(os.path, "exists", _exists_only("/usr/bin/tesseract"))
        d = cfg.describe_tesseract()
        assert d["installed"] is True and d["path"] == "/usr/bin/tesseract" and d["source"] == "path"
        assert "已改用 /usr/bin/tesseract" in d["hint"]

    def test_source_labels_cover_all_sources(self):
        assert set(cfg.TESSERACT_SOURCE_LABELS) == {"env", "path", "candidate"}


# ---------------------------------------------------------------------------
# DocumentLoader：缺失提示
# ---------------------------------------------------------------------------
class TestDocumentLoaderMissing:
    @pytest.fixture
    def image(self, tmp_path):
        from PIL import Image

        p = tmp_path / "scan.png"
        Image.new("RGB", (400, 200), color="white").save(p)
        return p

    def test_missing_disables_ocr_with_doc_hint(self, tmp_path, monkeypatch, capsys):
        import document_loader as dl

        monkeypatch.setattr(dl, "OCR_ENGINE", "tesseract")
        monkeypatch.setattr(dl, "describe_tesseract",
                            lambda: {"path": None, "source": None, "installed": False, "hint": cfg.TESSERACT_MISSING_HINT})
        loader = dl.DocumentLoader(tmp_path / "data", enable_ocr=True)
        out = capsys.readouterr().out
        assert loader.enable_ocr is False and loader.ocr_engine is None
        assert loader.ocr_unavailable_reason == cfg.TESSERACT_MISSING_HINT
        assert "未检测到 Tesseract" in out and "docs/tutorials/02-installation.md#ocr" in out
        # 不再出现"路径不存在"类的底层报错
        assert "No such file" not in out and "not installed or it's not in your PATH" not in out

    def test_image_skip_message_carries_reason(self, tmp_path, monkeypatch, capsys, image):
        import document_loader as dl

        monkeypatch.setattr(dl, "OCR_ENGINE", "tesseract")
        monkeypatch.setattr(dl, "describe_tesseract",
                            lambda: {"path": None, "source": None, "installed": False, "hint": cfg.TESSERACT_MISSING_HINT})
        loader = dl.DocumentLoader(tmp_path / "data", enable_ocr=True, enable_validation=False)
        capsys.readouterr()
        assert loader.load_file(image, enable_ocr=True) == []
        out = capsys.readouterr().out
        assert "未检测到 Tesseract" in out and "跳过图片文件: scan.png" in out

    def test_pdf_ocr_skip_message_carries_reason(self, tmp_path, monkeypatch, capsys):
        import document_loader as dl

        monkeypatch.setattr(dl, "OCR_ENGINE", "tesseract")
        monkeypatch.setattr(dl, "describe_tesseract",
                            lambda: {"path": None, "source": None, "installed": False, "hint": cfg.TESSERACT_MISSING_HINT})
        loader = dl.DocumentLoader(tmp_path / "data", enable_ocr=True, enable_validation=False)
        capsys.readouterr()
        assert loader._process_pdf_ocr(tmp_path / "x.pdf") == []
        assert "已跳过 x.pdf 中图片的 OCR" in capsys.readouterr().out

    def test_pdf_ocr_silent_when_no_reason(self, tmp_path, capsys):
        import document_loader as dl

        loader = dl.DocumentLoader(tmp_path / "data", enable_ocr=False, enable_validation=False)
        capsys.readouterr()
        assert loader._process_pdf_ocr(tmp_path / "x.pdf") == []
        assert capsys.readouterr().out == ""

    def test_found_path_is_passed_to_engine(self, tmp_path, monkeypatch):
        import document_loader as dl

        monkeypatch.setattr(dl, "OCR_ENGINE", "tesseract")
        monkeypatch.setattr(dl, "describe_tesseract",
                            lambda: {"path": "/usr/bin/tesseract", "source": "path", "installed": True, "hint": None})
        seen = {}

        class FakeEngine:
            def __init__(self, conf):
                seen.update(conf)

        fake_pkg = MagicMock(TesseractOCREngine=FakeEngine, PaddleOCREngine=MagicMock(), PDFImageExtractor=MagicMock())
        monkeypatch.setitem(sys.modules, "ocr_processor", fake_pkg)
        loader = dl.DocumentLoader(tmp_path / "data", enable_ocr=True, enable_validation=False)
        assert isinstance(loader.ocr_engine, FakeEngine)
        assert seen["tesseract_path"] == "/usr/bin/tesseract"
        assert loader.ocr_unavailable_reason is None

    def test_found_with_hint_prints_hint_but_continues(self, tmp_path, monkeypatch, capsys):
        import document_loader as dl

        monkeypatch.setattr(dl, "OCR_ENGINE", "tesseract")
        monkeypatch.setattr(dl, "describe_tesseract",
                            lambda: {"path": "/usr/bin/tesseract", "source": "path", "installed": True,
                                     "hint": "TESSERACT_PATH=/nope 指向的文件不存在，已改用 /usr/bin/tesseract"})
        fake_pkg = MagicMock(TesseractOCREngine=MagicMock(), PaddleOCREngine=MagicMock(), PDFImageExtractor=MagicMock())
        monkeypatch.setitem(sys.modules, "ocr_processor", fake_pkg)
        loader = dl.DocumentLoader(tmp_path / "data", enable_ocr=True, enable_validation=False)
        assert loader.enable_ocr is True
        assert "已改用 /usr/bin/tesseract" in capsys.readouterr().out

    def test_other_init_failures_still_recorded(self, tmp_path, monkeypatch, capsys):
        import document_loader as dl

        monkeypatch.setattr(dl, "OCR_ENGINE", "tesseract")
        monkeypatch.setattr(dl, "describe_tesseract",
                            lambda: {"path": "/usr/bin/tesseract", "source": "path", "installed": True, "hint": None})
        boom = MagicMock(side_effect=RuntimeError("lang pack missing"))
        fake_pkg = MagicMock(TesseractOCREngine=boom, PaddleOCREngine=MagicMock(), PDFImageExtractor=MagicMock())
        monkeypatch.setitem(sys.modules, "ocr_processor", fake_pkg)
        loader = dl.DocumentLoader(tmp_path / "data", enable_ocr=True, enable_validation=False)
        assert loader.enable_ocr is False
        assert "lang pack missing" in loader.ocr_unavailable_reason
        assert "OCR 初始化失败" in capsys.readouterr().out

    def test_skip_reason_fallbacks(self, tmp_path):
        import document_loader as dl

        loader = dl.DocumentLoader(tmp_path / "data", enable_ocr=False, enable_validation=False)
        assert loader.ocr_skip_reason() == "OCR 引擎未初始化"
        loader.ocr_engine = MagicMock()
        assert loader.ocr_skip_reason() == "OCR 未启用"
        loader.ocr_unavailable_reason = "自定义原因"
        assert loader.ocr_skip_reason() == "自定义原因"


class TestTesseractEngineMessage:
    def test_runtime_error_mentions_install_doc(self):
        pytest.importorskip("pytesseract")
        from ocr_processor.tesseract_ocr import TesseractOCREngine

        with patch("pytesseract.get_tesseract_version", side_effect=Exception("tesseract is not installed")):
            with pytest.raises(RuntimeError) as ei:
                TesseractOCREngine({"tesseract_path": None, "preprocess": False})
        msg = str(ei.value)
        assert "Tesseract 不可用" in msg and "docs/tutorials/02-installation.md#ocr" in msg


# ---------------------------------------------------------------------------
# CLI /config 与 check_knowledge_status
# ---------------------------------------------------------------------------
class TestCLIConfigRow:
    def test_row_present_installed(self, monkeypatch):
        import cli_handlers as h

        monkeypatch.setattr(cfg, "describe_tesseract",
                            lambda: {"path": "/usr/bin/tesseract", "source": "path", "installed": True, "hint": None})
        monkeypatch.setattr(cfg, "OCR_ENABLED", True)
        monkeypatch.setattr(cfg, "OCR_ENGINE", "tesseract")
        rows = dict(h.config_rows())
        assert rows["Tesseract（OCR）"] == "/usr/bin/tesseract（PATH 中找到）"

    def test_row_missing_has_doc_link(self, monkeypatch):
        import cli_handlers as h

        monkeypatch.setattr(cfg, "describe_tesseract",
                            lambda: {"path": None, "source": None, "installed": False, "hint": cfg.TESSERACT_MISSING_HINT})
        monkeypatch.setattr(cfg, "OCR_ENABLED", True)
        monkeypatch.setattr(cfg, "OCR_ENGINE", "tesseract")
        text = dict(h.config_rows())["Tesseract（OCR）"]
        assert text.startswith("未安装 —— ") and "02-installation.md#ocr" in text

    def test_row_notes_other_engine_or_disabled(self, monkeypatch):
        from cli.handlers.system import tesseract_row_text

        monkeypatch.setattr(cfg, "describe_tesseract",
                            lambda: {"path": "/opt/homebrew/bin/tesseract", "source": "candidate", "installed": True, "hint": None})
        monkeypatch.setattr(cfg, "OCR_ENABLED", True)
        monkeypatch.setattr(cfg, "OCR_ENGINE", "paddle")
        assert "当前 OCR_ENGINE=paddle" in tesseract_row_text()
        monkeypatch.setattr(cfg, "OCR_ENABLED", False)
        assert "OCR_ENABLED=false" in tesseract_row_text()
        assert "常见安装目录探测到" in tesseract_row_text()

    def test_row_appends_hint_when_found_elsewhere(self, monkeypatch):
        from cli.handlers.system import tesseract_row_text

        monkeypatch.setattr(cfg, "describe_tesseract",
                            lambda: {"path": "/usr/bin/tesseract", "source": "path", "installed": True,
                                     "hint": "TESSERACT_PATH=/nope 指向的文件不存在，已改用 /usr/bin/tesseract"})
        monkeypatch.setattr(cfg, "OCR_ENABLED", True)
        monkeypatch.setattr(cfg, "OCR_ENGINE", "tesseract")
        assert "已改用 /usr/bin/tesseract" in tesseract_row_text()

    def test_row_survives_probe_failure(self, monkeypatch):
        from cli.handlers.system import tesseract_row_text

        monkeypatch.setattr(cfg, "describe_tesseract", MagicMock(side_effect=RuntimeError("boom")))
        assert tesseract_row_text().startswith("探测失败")

    def test_handle_config_prints_tesseract(self, monkeypatch):
        import cli_handlers as h
        from query_interface import ParsedCommand

        monkeypatch.setattr(cfg, "describe_tesseract",
                            lambda: {"path": None, "source": None, "installed": False, "hint": cfg.TESSERACT_MISSING_HINT})
        ctx = h.CLIContext(console=MagicMock(), has_rich=False, registry=MagicMock(), record_command=MagicMock())
        assert h.handle_config(ctx, ParsedCommand("config", "/config")) is True
        out = "\n".join(str(c.args[0]) for c in ctx.console.print.call_args_list if c.args)
        assert "Tesseract（OCR）: 未安装" in out


class TestKnowledgeStatusTool:
    def test_status_lists_tesseract(self, monkeypatch):
        import agent_tools as at

        engine = MagicMock()
        engine.chroma_collection.count.return_value = 3
        engine.index = None
        monkeypatch.setattr(at, "_rag_engine", engine)
        monkeypatch.setattr(cfg, "OCR_ENABLED", True)
        monkeypatch.setattr(cfg, "OCR_ENGINE", "tesseract")
        monkeypatch.setattr(cfg, "describe_tesseract",
                            lambda: {"path": "/usr/bin/tesseract", "source": "path", "installed": True, "hint": None})
        assert "Tesseract: /usr/bin/tesseract" in at.check_knowledge_status()
        monkeypatch.setattr(cfg, "describe_tesseract",
                            lambda: {"path": None, "source": None, "installed": False, "hint": cfg.TESSERACT_MISSING_HINT})
        out = at.check_knowledge_status()
        assert "⚠️ Tesseract: 未检测到 Tesseract" in out and "02-installation.md#ocr" in out


# ---------------------------------------------------------------------------
# Web 系统页
# ---------------------------------------------------------------------------
class TestWebSystemPage:
    def test_env_info_includes_probe(self, monkeypatch):
        from web.services import WebService

        monkeypatch.setattr(cfg, "describe_tesseract",
                            lambda: {"path": "/usr/bin/tesseract", "source": "path", "installed": True, "hint": None})
        monkeypatch.setattr(cfg, "OCR_ENABLED", True)
        monkeypatch.setattr(cfg, "OCR_ENGINE", "tesseract")
        with patch("llm_client.describe_backend", return_value={"provider": "ollama", "base_url": "http://o", "healthy": True}):
            info = WebService().env_info()
        assert info["tesseract_path"] == "/usr/bin/tesseract"
        assert info["tesseract_source"] == "path" and info["tesseract_hint"] is None
        assert info["ocr_engine"] == "tesseract" and info["ocr_enabled"] is True

    def test_env_info_probe_failure(self, monkeypatch):
        from web.services import WebService

        monkeypatch.setattr(cfg, "describe_tesseract", MagicMock(side_effect=RuntimeError("boom")))
        with patch("llm_client.describe_backend", return_value={"provider": "ollama", "base_url": "http://o", "healthy": True}):
            info = WebService().env_info()
        assert info["tesseract_path"] is None and "探测失败" in info["tesseract_hint"]

    def test_format_installed(self):
        from web.app import format_env_info

        md = format_env_info({"tesseract_path": "/opt/homebrew/bin/tesseract", "tesseract_source": "candidate",
                              "tesseract_hint": None, "ocr_enabled": True, "ocr_engine": "tesseract"})
        assert "| Tesseract（OCR） | ✅ `/opt/homebrew/bin/tesseract`（常见安装目录探测到） |" in md

    def test_format_missing_with_doc_link(self):
        from web.app import format_env_info

        md = format_env_info({"tesseract_path": None, "tesseract_source": None,
                              "tesseract_hint": cfg.TESSERACT_MISSING_HINT, "ocr_enabled": True, "ocr_engine": "tesseract"})
        assert "❌ 未安装 —— 未检测到 Tesseract" in md and "02-installation.md#ocr" in md

    def test_format_notes_engine_and_hint(self):
        from web.app import format_env_info

        md = format_env_info({"tesseract_path": "/usr/bin/tesseract", "tesseract_source": "path",
                              "tesseract_hint": "TESSERACT_PATH=/nope 指向的文件不存在，已改用 /usr/bin/tesseract",
                              "ocr_enabled": False, "ocr_engine": "paddle"})
        assert "已改用 /usr/bin/tesseract" in md and "`OCR_ENGINE=paddle`" in md and "`OCR_ENABLED=false`" in md
        # 缺提示 + 缺路径也有合理兜底
        md2 = format_env_info({"tesseract_path": None})
        assert "❌ 未安装 —— 安装方法见 docs/tutorials/02-installation.md#ocr" in md2

    def test_format_row_absent_when_info_lacks_probe(self):
        from web.app import format_env_info

        assert "Tesseract" not in format_env_info({"cwd": "/w"})


# ---------------------------------------------------------------------------
# bootstrap：仅提示一次
# ---------------------------------------------------------------------------
@pytest.fixture
def bootstrap_fresh(monkeypatch, tmp_path):
    """进程内标记复位 + 持久标记落到临时目录。"""
    import bootstrap
    import runtime_paths as rp

    monkeypatch.setattr(bootstrap, "_tesseract_hint_shown_in_process", False)
    saved = rp._APP_STATE_ROOT_OVERRIDE
    rp.set_app_state_root(tmp_path / "state")
    try:
        yield bootstrap, tmp_path / "state"
    finally:
        rp.set_app_state_root(saved)


def _missing(monkeypatch):
    monkeypatch.setattr(cfg, "OCR_ENABLED", True)
    monkeypatch.setattr(cfg, "OCR_ENGINE", "tesseract")
    monkeypatch.setattr(cfg, "describe_tesseract",
                        lambda: {"path": None, "source": None, "installed": False, "hint": cfg.TESSERACT_MISSING_HINT})


class TestBootstrapCheckTesseract:
    def test_installed_returns_none_and_silent(self, bootstrap_fresh, monkeypatch, capsys):
        bootstrap, _ = bootstrap_fresh
        monkeypatch.setattr(cfg, "OCR_ENABLED", True)
        monkeypatch.setattr(cfg, "OCR_ENGINE", "tesseract")
        monkeypatch.setattr(cfg, "describe_tesseract",
                            lambda: {"path": "/usr/bin/tesseract", "source": "path", "installed": True, "hint": None})
        notes = []
        assert bootstrap.check_tesseract(notify=lambda t, m: notes.append((t, m))) is None
        assert notes == [] and capsys.readouterr().out == ""

    def test_missing_notifies_once_and_writes_marker(self, bootstrap_fresh, monkeypatch, capsys):
        bootstrap, state = bootstrap_fresh
        _missing(monkeypatch)
        notes = []
        hint = bootstrap.check_tesseract(notify=lambda t, m: notes.append((t, m)))
        assert hint == cfg.TESSERACT_MISSING_HINT
        assert len(notes) == 1 and "Tesseract" in notes[0][0] and "02-installation.md#ocr" in notes[0][1]
        assert "OCR 为可选功能" in notes[0][1]
        assert (state / bootstrap.TESSERACT_HINT_MARKER).exists()
        assert "[Cerebro] 未检测到 Tesseract" in capsys.readouterr().out
        # 第二次：进程内标记生效，不再提示
        assert bootstrap.check_tesseract(notify=lambda t, m: notes.append((t, m))) is None
        assert len(notes) == 1

    def test_persistent_marker_suppresses_next_process(self, bootstrap_fresh, monkeypatch):
        bootstrap, state = bootstrap_fresh
        _missing(monkeypatch)
        state.mkdir(parents=True)
        (state / bootstrap.TESSERACT_HINT_MARKER).write_text("shown")
        notes = []
        assert bootstrap.check_tesseract(notify=lambda t, m: notes.append((t, m))) is None
        assert notes == [] and bootstrap._tesseract_hint_shown_in_process is False

    def test_once_false_always_notifies(self, bootstrap_fresh, monkeypatch):
        bootstrap, _ = bootstrap_fresh
        _missing(monkeypatch)
        notes = []
        for _ in range(2):
            assert bootstrap.check_tesseract(notify=lambda t, m: notes.append((t, m)), once=False)
        assert len(notes) == 2

    def test_marker_unwritable_falls_back_to_process_flag(self, bootstrap_fresh, monkeypatch):
        bootstrap, _ = bootstrap_fresh
        _missing(monkeypatch)
        bad = MagicMock()
        bad.exists.return_value = False
        bad.parent.mkdir.side_effect = OSError("ro")
        monkeypatch.setattr(bootstrap, "_tesseract_marker_path", lambda: bad)
        assert bootstrap.check_tesseract() == cfg.TESSERACT_MISSING_HINT
        assert bootstrap.check_tesseract() is None

    def test_marker_path_failure_returns_none_path(self, bootstrap_fresh, monkeypatch):
        bootstrap, _ = bootstrap_fresh
        _missing(monkeypatch)
        monkeypatch.setitem(sys.modules, "runtime_paths", None)
        assert bootstrap._tesseract_marker_path() is None
        assert bootstrap.check_tesseract() == cfg.TESSERACT_MISSING_HINT

    def test_skipped_when_ocr_disabled_or_other_engine(self, bootstrap_fresh, monkeypatch):
        bootstrap, _ = bootstrap_fresh
        monkeypatch.setattr(cfg, "describe_tesseract", MagicMock(side_effect=AssertionError("must not probe")))
        monkeypatch.setattr(cfg, "OCR_ENABLED", False)
        monkeypatch.setattr(cfg, "OCR_ENGINE", "tesseract")
        assert bootstrap.check_tesseract() is None
        monkeypatch.setattr(cfg, "OCR_ENABLED", True)
        monkeypatch.setattr(cfg, "OCR_ENGINE", "paddle")
        assert bootstrap.check_tesseract() is None

    def test_probe_exception_is_swallowed(self, bootstrap_fresh, monkeypatch):
        bootstrap, _ = bootstrap_fresh
        monkeypatch.setattr(cfg, "OCR_ENABLED", True)
        monkeypatch.setattr(cfg, "OCR_ENGINE", "tesseract")
        monkeypatch.setattr(cfg, "describe_tesseract", MagicMock(side_effect=RuntimeError("boom")))
        assert bootstrap.check_tesseract() is None

    def test_notify_exception_is_swallowed(self, bootstrap_fresh, monkeypatch):
        bootstrap, _ = bootstrap_fresh
        _missing(monkeypatch)
        assert bootstrap.check_tesseract(notify=MagicMock(side_effect=RuntimeError("gui"))) == cfg.TESSERACT_MISSING_HINT

    def test_ensure_ollama_ready_runs_check_even_when_backend_fails(self, bootstrap_fresh, monkeypatch):
        bootstrap, _ = bootstrap_fresh
        _missing(monkeypatch)
        notes = []
        monkeypatch.setattr(bootstrap, "llm_provider", lambda: "ollama")
        monkeypatch.setattr(bootstrap, "ollama_running", lambda: False)
        monkeypatch.setattr(bootstrap, "ollama_installed", lambda: False)
        ok = bootstrap.ensure_ollama_ready(interactive=False, notify=lambda t, m: notes.append((t, m)))
        assert ok is False
        titles = [t for t, _ in notes]
        assert titles[0] == "需要安装 Ollama"            # 先 LLM 后端，再 Tesseract
        assert any("Tesseract" in t for t in titles)

    def test_ensure_ollama_ready_success_path_checks_tesseract(self, bootstrap_fresh, monkeypatch):
        bootstrap, _ = bootstrap_fresh
        _missing(monkeypatch)
        notes = []
        monkeypatch.setattr(bootstrap, "llm_provider", lambda: "ollama")
        monkeypatch.setattr(bootstrap, "ollama_running", lambda: True)
        monkeypatch.setattr(bootstrap, "missing_models", lambda req: [])
        assert bootstrap.ensure_ollama_ready(interactive=False, notify=lambda t, m: notes.append((t, m))) is True
        assert len(notes) == 1 and "Tesseract" in notes[0][0]
