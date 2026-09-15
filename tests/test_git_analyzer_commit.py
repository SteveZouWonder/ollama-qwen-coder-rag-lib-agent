#!/usr/bin/env python3
"""test_git_analyzer_commit.py — 共享层 ``GitAnalyzer.get_commit_preview / commit / _run_git_full``（F9 P3-3）。

用真实临时仓库（还原 conftest 对 subprocess 的全局 Mock）。
"""
import subprocess
from unittest.mock import MagicMock

_REAL_RUN = subprocess.run
_REAL_POPEN = subprocess.Popen

import pytest

from git_integration.git_analyzer import GitAnalyzer


@pytest.fixture(autouse=True)
def _real_git(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _REAL_RUN)
    monkeypatch.setattr(subprocess, "Popen", _REAL_POPEN)


def _repo(path, commits=1):
    def git(*args):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True, encoding="utf-8")

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "Tester")
    for i in range(commits):
        (path / f"f{i}.txt").write_text(f"v{i}\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-q", "-m", f"commit {i}")
    return git


class TestCommitPreview:
    def test_empty_stage(self, tmp_path):
        _repo(tmp_path)
        pv = GitAnalyzer(str(tmp_path)).get_commit_preview()
        assert pv == {"is_repo": True, "has_staged": False, "staged_files": [], "diff_stat": "",
                      "files_changed": 0, "insertions": 0, "deletions": 0}

    def test_staged_statuses_and_stats(self, tmp_path):
        git = _repo(tmp_path, commits=2)
        (tmp_path / "f0.txt").write_text("a\nb\nc\n", encoding="utf-8")   # 修改：+3 -1
        (tmp_path / "f1.txt").unlink()                                     # 删除：-1
        (tmp_path / "new.txt").write_text("x\n", encoding="utf-8")         # 新增：+1
        git("add", "-A")
        pv = GitAnalyzer(str(tmp_path)).get_commit_preview()
        assert pv["has_staged"] is True
        assert {f["path"]: (f["status"], f["label"]) for f in pv["staged_files"]} == {
            "f0.txt": ("M", "修改"), "f1.txt": ("D", "删除"), "new.txt": ("A", "新增"),
        }
        assert pv["files_changed"] == 3 and pv["insertions"] == 4 and pv["deletions"] == 2
        assert "3 files changed" in pv["diff_stat"]

    def test_rename_takes_new_path(self, tmp_path):
        git = _repo(tmp_path)
        git("mv", "f0.txt", "moved.txt")
        pv = GitAnalyzer(str(tmp_path)).get_commit_preview()
        assert pv["staged_files"] == [{"status": "R100", "label": "重命名", "path": "moved.txt"}]
        assert pv["files_changed"] == 1 and pv["insertions"] == 0

    def test_non_repo(self, tmp_path):
        pv = GitAnalyzer(str(tmp_path)).get_commit_preview()
        assert pv["is_repo"] is False and pv["has_staged"] is False


class TestCommit:
    def test_success(self, tmp_path):
        git = _repo(tmp_path)
        (tmp_path / "f0.txt").write_text("changed\n", encoding="utf-8")
        git("add", ".")
        r = GitAnalyzer(str(tmp_path)).commit("feat: 标题\n\n正文说明")
        assert r["ok"] is True and len(r["hash7"]) >= 7 and r["subject"] == "feat: 标题" and r["error"] == ""
        log = subprocess.run(
            ["git", "log", "-1", "--format=%B"], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8",
        ).stdout  # 显式 UTF-8：Windows 默认 cp1252 会把中文提交信息解成乱码
        assert "正文说明" in log
        assert GitAnalyzer(str(tmp_path)).get_commit_preview()["has_staged"] is False

    def test_guards(self, tmp_path):
        _repo(tmp_path)
        an = GitAnalyzer(str(tmp_path))
        assert an.commit("   ")["error"] == "提交信息不能为空"
        assert "暂存区为空" in an.commit("x")["error"]
        other = tmp_path / "sub"
        other.mkdir()
        # 子目录仍在工作区内 → 是仓库；用 monkeypatch 模拟非仓库
        an2 = GitAnalyzer(str(other))
        an2.is_repo = lambda: False
        assert an2.commit("x")["error"] == "当前目录不是 Git 仓库"

    def test_git_failure_surfaces_stderr(self, tmp_path, monkeypatch):
        git = _repo(tmp_path)
        (tmp_path / "f0.txt").write_text("changed\n", encoding="utf-8")
        git("add", ".")
        an = GitAnalyzer(str(tmp_path))
        monkeypatch.setattr(an, "_run_git_full", lambda cmd: {"returncode": 1, "stdout": "", "stderr": "hook rejected"})
        r = an.commit("x")
        assert r["ok"] is False and r["error"] == "hook rejected"
        monkeypatch.setattr(an, "_run_git_full", lambda cmd: {"returncode": 2, "stdout": "", "stderr": ""})
        assert "退出码 2" in an.commit("x")["error"]


class TestRunGitFull:
    def test_ok_and_error(self, tmp_path):
        _repo(tmp_path)
        an = GitAnalyzer(str(tmp_path))
        ok = an._run_git_full(["rev-parse", "--is-inside-work-tree"])
        assert ok["returncode"] == 0 and ok["stdout"] == "true"
        bad = an._run_git_full(["nonsense-subcommand"])
        assert bad["returncode"] != 0 and bad["stderr"]

    def test_timeout_and_exception(self, tmp_path, monkeypatch):
        an = GitAnalyzer(str(tmp_path))

        def timeout(*a, **k):
            raise subprocess.TimeoutExpired(cmd="git", timeout=30)

        monkeypatch.setattr(subprocess, "run", timeout)
        r = an._run_git_full(["status"])
        assert r["returncode"] == 124 and "超时" in r["stderr"]

        def boom(*a, **k):
            raise OSError("no git")

        monkeypatch.setattr(subprocess, "run", boom)
        r = an._run_git_full(["status"])
        assert r["returncode"] == 1 and r["stderr"] == "no git"


class TestCommitGeneratorRequest:
    """AI 生成提交信息的请求选项：``think=False`` + ``num_predict`` 限额（提示词本身不改，A-4）。"""

    def test_request_payload_and_parse(self, monkeypatch):
        from git_integration import commit_generator as cg

        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured.update(url=url, json=json, timeout=timeout)
            return MagicMock(status_code=200, json=lambda: {"message": {"content": "feat: add sub\n\n详情"}})

        monkeypatch.setattr(cg, "requests", MagicMock(post=fake_post), raising=False)
        import requests as real_requests
        monkeypatch.setattr(real_requests, "post", fake_post)
        gen = cg.CommitMessageGenerator(".", model="m")
        s = gen._generate_ai_commit_message("diff --git a b")
        assert s.title == "feat: add sub" and s.body == "详情" and s.conventional_type == "feat"
        # F10 P1-2：由 /api/generate 改为经 llm_client 的 chat 消息格式（/api/chat）
        assert captured["url"].endswith("/api/chat") and captured["timeout"] == 60
        assert captured["json"]["think"] is False and captured["json"]["stream"] is False
        assert captured["json"]["options"] == {"num_predict": cg.CommitMessageGenerator.NUM_PREDICT}
        prompt = captured["json"]["messages"][0]["content"]
        assert captured["json"]["messages"][0]["role"] == "user"
        assert "Conventional Commits" in prompt and "diff --git a b" in prompt

    def test_non_200_falls_back(self, monkeypatch):
        from git_integration import commit_generator as cg
        import requests as real_requests

        monkeypatch.setattr(real_requests, "post", lambda *a, **k: MagicMock(status_code=500))
        s = cg.CommitMessageGenerator(".", model="m")._generate_ai_commit_message("new file mode x.py")
        assert s.title.startswith(("Add", "Update"))
